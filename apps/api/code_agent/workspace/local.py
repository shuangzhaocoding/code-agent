from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException

from code_agent.async_io import run_sync
from code_agent.config import settings
from code_agent.db.models import Workspace
from code_agent.policy.engine import is_protected
from code_agent.tools import paths as path_tools


class LocalWorkspaceBackend:
    kind = "local"

    def __init__(self, ws: Workspace) -> None:
        self._ws = ws
        self.root_path = ws.root_path

    async def list_dir(self, rel: str = "", extra_ignores: list[str] | None = None) -> list[dict]:
        ignores = list(self._ws.ignore_globs or []) + (extra_ignores or [])
        return await run_sync(path_tools.list_dir, self.root_path, rel, ignores)

    async def read_text(self, rel: str, max_bytes: int | None = None) -> str:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        return await run_sync(path_tools.read_text_file, path, max_bytes)

    async def read_bytes(self, rel: str, max_bytes: int | None = None) -> bytes:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        limit = max_bytes or int(settings.get("workspace.max_file_bytes") or 1048576)

        def _read() -> bytes:
            if not path.is_file():
                raise HTTPException(status_code=404, detail={"code": "path.not_found"})
            size = path.stat().st_size
            if size > limit:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "file.too_large", "message": f"File exceeds {limit} bytes"},
                )
            return path.read_bytes()

        return await run_sync(_read)

    async def write_text(self, rel: str, content: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        await run_sync(_write)

    async def mkdir(self, rel: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        await run_sync(path.mkdir, parents=True, exist_ok=False)

    async def create_file(self, rel: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)

        def _create() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

        await run_sync(_create)

    async def rename(self, src: str, dest: str) -> None:
        sp = path_tools.resolve_in_workspace(self.root_path, src)
        dp = path_tools.resolve_in_workspace(self.root_path, dest)

        def _rename() -> None:
            dp.parent.mkdir(parents=True, exist_ok=True)
            sp.rename(dp)

        await run_sync(_rename)

    async def delete(self, rel: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)

        def _delete() -> None:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

        await run_sync(_delete)

    async def exists(self, rel: str = ".") -> bool:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        return await run_sync(path.exists)

    async def is_dir(self, rel: str = ".") -> bool:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        return await run_sync(path.is_dir)

    async def is_file(self, rel: str) -> bool:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        return await run_sync(path.is_file)

    async def walk_files(
        self, extra_ignores: list[str] | None = None, limit: int = 5000
    ) -> list[tuple[str, str]]:
        ignores = list(self._ws.ignore_globs or []) + (extra_ignores or [])

        def _walk() -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for rel, p in path_tools.walk_files(self.root_path, ignores, limit):
                out.append((rel, str(p)))
            return out

        return await run_sync(_walk)

    async def search(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_hits: int | None = None,
    ) -> list[dict]:
        _ = regex  # local search is literal; remote may use rg -F / regex later
        return await run_sync(
            path_tools.search_file_contents,
            self.root_path,
            query,
            extra_ignores=list(self._ws.ignore_globs or []),
            limit=max_hits or 80,
            includes=include,
            excludes=exclude,
            case_sensitive=case_sensitive,
        )

    async def run_command(
        self, command: str, *, cwd: str = ".", timeout: int = 90
    ) -> tuple[int, str, str]:
        work = path_tools.resolve_in_workspace(self.root_path, cwd)
        if not await run_sync(work.is_dir):
            work = Path(self.root_path)

        def _run() -> tuple[int, str, str]:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""

        try:
            return await run_sync(_run)
        except subprocess.TimeoutExpired:
            return 124, "", f"command timed out after {timeout}s"

    async def close(self) -> None:
        return None


def assert_not_protected(rel: str) -> None:
    if is_protected(rel):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
