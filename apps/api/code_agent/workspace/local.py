from __future__ import annotations

import asyncio
import os
import shutil
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
            with path.open("rb") as fh:
                return fh.read(limit)

        return await run_sync(_read)

    async def write_text(self, rel: str, content: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        await run_sync(path_tools.write_text_file, path, content)

    async def write_bytes(self, rel: str, content: bytes) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        await run_sync(_write)

    async def mkdir(self, rel: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        await run_sync(path.mkdir, parents=True, exist_ok=False)

    async def create_file(self, rel: str) -> None:
        path = path_tools.resolve_in_workspace(self.root_path, rel)
        await run_sync(path_tools.write_text_file, path, "")

    async def rename(self, src: str, dest: str) -> None:
        sp = path_tools.resolve_in_workspace(self.root_path, src)
        dp = path_tools.resolve_in_workspace(self.root_path, dest)

        def _rename() -> None:
            dp.parent.mkdir(parents=True, exist_ok=True)
            sp.rename(dp)

        await run_sync(_rename)

    async def copy(self, src: str, dest: str) -> None:
        sp = path_tools.resolve_in_workspace(self.root_path, src)
        dp = path_tools.resolve_in_workspace(self.root_path, dest)

        def _copy() -> None:
            if not sp.exists():
                raise HTTPException(status_code=404, detail={"code": "path.not_found"})
            if dp.exists():
                raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
            dp.parent.mkdir(parents=True, exist_ok=True)
            if sp.is_dir():
                shutil.copytree(sp, dp)
            else:
                shutil.copy2(sp, dp)

        await run_sync(_copy)

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
        self,
        extra_ignores: list[str] | None = None,
        limit: int = 5000,
        root_rel: str = "",
    ) -> list[tuple[str, str]]:
        ignores = list(self._ws.ignore_globs or []) + (extra_ignores or [])
        start = (root_rel or "").strip().replace("\\", "/").strip("/")

        def _walk() -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for rel, p in path_tools.walk_files(self.root_path, ignores, limit, root_rel=start):
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
        self,
        command: str,
        *,
        cwd: str = ".",
        timeout: int = 90,
        cancel_event: asyncio.Event | None = None,
        on_output=None,
    ) -> tuple[int, str, str]:
        work = path_tools.resolve_in_workspace(self.root_path, cwd)
        if not await run_sync(work.is_dir):
            work = Path(self.root_path)

        from code_agent.runtime.python_env import merge_python_env, resolve_python_env

        pyenv = resolve_python_env(workspace_root=self.root_path)
        env = merge_python_env(os.environ, pyenv)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(work),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
        except Exception as exc:
            return 1, "", str(exc)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def _pump(stream: asyncio.StreamReader | None, sink: list[str]) -> None:
            if not stream:
                return
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                text = chunk.decode(errors="replace")
                sink.append(text)
                if on_output:
                    try:
                        await on_output(text)
                    except Exception:
                        pass

        pump_out = asyncio.create_task(_pump(proc.stdout, stdout_parts))
        pump_err = asyncio.create_task(_pump(proc.stderr, stderr_parts))
        wait_task = asyncio.create_task(proc.wait())
        cancel_task: asyncio.Task | None = None
        if cancel_event is not None:
            cancel_task = asyncio.create_task(cancel_event.wait())

        def _kill() -> None:
            if proc.returncode is not None:
                return
            try:
                if hasattr(os, "killpg") and proc.pid:
                    os.killpg(proc.pid, 15)
                else:
                    proc.terminate()
            except ProcessLookupError:
                return
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        timed_out = False
        cancelled = False
        try:
            waiters: set[asyncio.Task] = {wait_task}
            if cancel_task:
                waiters.add(cancel_task)
            done, _pending = await asyncio.wait(
                waiters,
                timeout=max(1, int(timeout or 90)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task and cancel_task in done and cancel_event and cancel_event.is_set():
                cancelled = True
                _kill()
            elif wait_task not in done:
                timed_out = True
                _kill()
            if wait_task not in done:
                try:
                    await asyncio.wait_for(wait_task, timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        await wait_task
                    except Exception:
                        pass
        finally:
            if cancel_task and not cancel_task.done():
                cancel_task.cancel()
            await asyncio.gather(pump_out, pump_err, return_exceptions=True)

        out = "".join(stdout_parts)
        err = "".join(stderr_parts)
        if cancelled:
            return 130, out, (err + ("\n" if err else "") + "command cancelled")
        if timed_out:
            return 124, out, (err + ("\n" if err else "") + f"command timed out after {timeout}s")
        return int(proc.returncode or 0), out, err

    async def close(self) -> None:
        return None


def assert_not_protected(rel: str) -> None:
    if is_protected(rel):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
