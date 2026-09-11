from __future__ import annotations

from pathlib import Path

from code_agent.routers.workspaces import _arcname_for, _archive_prefix
from code_agent.tools.paths import walk_files


def test_archive_prefix_and_arcname():
    assert _archive_prefix("") == ""
    assert _archive_prefix(".") == ""
    assert _archive_prefix("src/app") == "src/app"
    assert _arcname_for("src/app/main.ts", "src/app", "app") == "app/main.ts"
    assert _arcname_for("readme.md", "", "workspace") == "readme.md"


def test_walk_files_root_rel(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "sub" / "nested").mkdir()
    (tmp_path / "sub" / "nested" / "c.txt").write_text("c", encoding="utf-8")

    all_rels = [rel for rel, _ in walk_files(str(tmp_path), limit=50)]
    assert "a.txt" in all_rels
    assert "sub/b.txt" in all_rels

    sub_rels = [rel for rel, _ in walk_files(str(tmp_path), limit=50, root_rel="sub")]
    assert "a.txt" not in sub_rels
    assert "sub/b.txt" in sub_rels
    assert "sub/nested/c.txt" in sub_rels
