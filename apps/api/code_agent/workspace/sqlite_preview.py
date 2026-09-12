from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

SQLITE_MAGIC = b"SQLite format 3\x00"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200
MAX_CELL_CHARS = 1024
COUNT_TIMEOUT_SEC = 2.0
INTERNAL_PREFIX = "sqlite_"


class SqlitePreviewError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def looks_like_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def connect_readonly(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SqlitePreviewError(404, "path.not_found", "文件不存在")
    if not looks_like_sqlite(resolved):
        raise SqlitePreviewError(400, "sqlite.invalid", "不是有效的 SQLite 数据库")
    uri = resolved.as_uri()
    last_err: sqlite3.Error | None = None
    for suffix in ("?mode=ro", "?mode=ro&immutable=1"):
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(uri + suffix, uri=True, timeout=2.0)
            conn.execute("PRAGMA query_only=ON")
            return conn
        except sqlite3.Error as err:
            last_err = err
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
    raise SqlitePreviewError(400, "sqlite.open_failed", str(last_err or "无法打开数据库"))


def _list_objects(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT name, type FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND name NOT LIKE 'SQLITE_%'
        ORDER BY type ASC, name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [(str(name), str(kind)) for name, kind in rows if name]


def _table_columns(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    info = conn.execute(f"PRAGMA table_info({quote_ident(name)})").fetchall()
    columns: list[dict[str, Any]] = []
    for row in info:
        columns.append(
            {
                "name": str(row[1]),
                "type": str(row[2] or ""),
                "notnull": bool(row[3]),
                "pk": int(row[5] or 0),
            }
        )
    return columns


def _count_rows(conn: sqlite3.Connection, name: str) -> int | None:
    quoted = quote_ident(name)
    started = time.monotonic()

    def _progress() -> int:
        return 1 if time.monotonic() - started > COUNT_TIMEOUT_SEC else 0

    conn.set_progress_handler(_progress, 100_000)
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None
    finally:
        conn.set_progress_handler(None, 0)


def inspect_sqlite(path: Path) -> dict[str, Any]:
    conn = connect_readonly(path)
    try:
        objects = _list_objects(conn)
        tables: list[dict[str, Any]] = []
        for name, kind in objects:
            columns = _table_columns(conn, name)
            row_count = _count_rows(conn, name)
            tables.append(
                {
                    "name": name,
                    "type": kind,
                    "row_count": row_count,
                    "columns": columns,
                }
            )
        return {"tables": tables}
    finally:
        conn.close()


def _resolve_object(conn: sqlite3.Connection, table: str) -> tuple[str, str]:
    wanted = (table or "").strip()
    if not wanted or wanted.lower().startswith(INTERNAL_PREFIX):
        raise SqlitePreviewError(400, "sqlite.table_invalid", "无效的表名")
    for name, kind in _list_objects(conn):
        if name == wanted:
            return name, kind
    raise SqlitePreviewError(404, "sqlite.table_not_found", "表或视图不存在")


def serialize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        return {"$blob": len(value)}
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    text = value if isinstance(value, str) else str(value)
    if len(text) > MAX_CELL_CHARS:
        return text[:MAX_CELL_CHARS] + "…"
    return text


def query_sqlite(path: Path, table: str, offset: int = 0, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    if offset < 0:
        raise SqlitePreviewError(400, "sqlite.offset_invalid", "offset 不能为负")
    page = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    conn = connect_readonly(path)
    try:
        name, kind = _resolve_object(conn, table)
        quoted = quote_ident(name)
        cursor = conn.execute(f"SELECT * FROM {quoted} LIMIT ? OFFSET ?", (page, offset))
        col_names = [str(item[0]) for item in (cursor.description or [])]
        rows = [[serialize_cell(cell) for cell in row] for row in cursor.fetchall()]
        total = _count_rows(conn, name)
        return {
            "table": name,
            "type": kind,
            "offset": offset,
            "limit": page,
            "total": total,
            "columns": col_names,
            "rows": rows,
        }
    finally:
        conn.close()
