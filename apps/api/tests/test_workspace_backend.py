from __future__ import annotations

import asyncio
from pathlib import Path

from code_agent.workspace.local import LocalWorkspaceBackend


class _Ws:
    root_path = ""
    ignore_globs: list = []
    kind = "local"


def test_local_backend_list_and_read(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("print(1)\n", encoding="utf-8")
    ws = _Ws()
    ws.root_path = str(tmp_path)
    backend = LocalWorkspaceBackend(ws)  # type: ignore[arg-type]

    async def _run():
        items = await backend.list_dir(".")
        names = {i["name"] for i in items}
        assert "a.txt" in names
        assert "sub" in names
        text = await backend.read_text("a.txt")
        assert "hello" in text
        code, out, err = await backend.run_command("echo ok", cwd=".")
        assert code == 0
        assert "ok" in out

    asyncio.run(_run())


def test_list_dir_marks_gitignore(tmp_path: Path):
    (tmp_path / "keep.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "skip.log").write_text("nope\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "app.js").write_text("x\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.log\ndist/\n", encoding="utf-8")
    ws = _Ws()
    ws.root_path = str(tmp_path)
    backend = LocalWorkspaceBackend(ws)  # type: ignore[arg-type]

    async def _run():
        items = await backend.list_dir(".")
        by_name = {i["name"]: i for i in items}
        assert by_name["keep.txt"]["ignored"] is False
        assert by_name["skip.log"]["ignored"] is True
        assert by_name["dist"]["ignored"] is True
        nested = await backend.list_dir("dist")
        assert nested[0]["ignored"] is True

    asyncio.run(_run())


def test_local_write_text_preserves_crlf(tmp_path: Path):
    """Windows CRLF must round-trip; Path.write_text would turn \\r\\n into \\r\\r\\n."""
    rel = "main.py"
    original = b"print(1)\r\nprint(2)\r\n"
    (tmp_path / rel).write_bytes(original)
    ws = _Ws()
    ws.root_path = str(tmp_path)
    backend = LocalWorkspaceBackend(ws)  # type: ignore[arg-type]

    async def _run():
        text = await backend.read_text(rel)
        assert text == "print(1)\r\nprint(2)\r\n"
        await backend.write_text(rel, text)
        assert (tmp_path / rel).read_bytes() == original
        # Simulate editor save of CRLF content again — must not stack CRs.
        await backend.write_text(rel, text)
        assert (tmp_path / rel).read_bytes() == original

    asyncio.run(_run())
