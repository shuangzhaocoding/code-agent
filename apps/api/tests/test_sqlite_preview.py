from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from code_agent.workspace.sqlite_preview import (
    SqlitePreviewError,
    inspect_sqlite,
    query_sqlite,
    serialize_cell,
)


def _make_db(tmp_path: Path) -> Path:
    path = tmp_path / "app.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                score REAL,
                avatar BLOB,
                note TEXT
            );
            CREATE TABLE "order items" (
                id INTEGER PRIMARY KEY,
                qty INTEGER
            );
            CREATE VIEW active_users AS SELECT id, name FROM users WHERE score IS NOT NULL;
            INSERT INTO users (id, name, score, avatar, note)
            VALUES (1, 'alice', 1.5, X'00FF', NULL);
            INSERT INTO users (id, name, score, avatar, note)
            VALUES (2, 'bob', NULL, NULL, 'ok');
            INSERT INTO "order items" (id, qty) VALUES (1, 3);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_inspect_lists_tables_and_views(tmp_path: Path):
    meta = inspect_sqlite(_make_db(tmp_path))
    names = [row["name"] for row in meta["tables"]]
    assert names == ["order items", "users", "active_users"]
    by_name = {row["name"]: row for row in meta["tables"]}
    assert by_name["users"]["type"] == "table"
    assert by_name["users"]["row_count"] == 2
    assert by_name["active_users"]["type"] == "view"
    assert by_name["active_users"]["row_count"] == 1
    cols = {col["name"]: col for col in by_name["users"]["columns"]}
    assert cols["id"]["pk"] == 1
    assert cols["name"]["notnull"] is True


def test_query_paginates_and_serializes(tmp_path: Path):
    path = _make_db(tmp_path)
    page = query_sqlite(path, "users", offset=0, limit=1)
    assert page["total"] == 2
    assert page["columns"] == ["id", "name", "score", "avatar", "note"]
    assert page["rows"][0][0] == 1
    assert page["rows"][0][1] == "alice"
    assert page["rows"][0][3] == {"$blob": 2}
    assert page["rows"][0][4] is None
    page2 = query_sqlite(path, "users", offset=1, limit=1)
    assert page2["rows"][0][1] == "bob"


def test_quoted_table_name_and_injection_rejected(tmp_path: Path):
    path = _make_db(tmp_path)
    page = query_sqlite(path, "order items")
    assert page["total"] == 1
    assert page["rows"][0][1] == 3
    with pytest.raises(SqlitePreviewError) as exc:
        query_sqlite(path, "users; DROP TABLE users")
    assert exc.value.code == "sqlite.table_not_found"


def test_rejects_non_sqlite(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(SqlitePreviewError) as exc:
        inspect_sqlite(path)
    assert exc.value.code == "sqlite.invalid"


def test_serialize_cell_truncates_long_text():
    long = "x" * 2000
    out = serialize_cell(long)
    assert isinstance(out, str)
    assert out.endswith("…")
    assert len(out) == 1025
