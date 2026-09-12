from __future__ import annotations

import asyncio
import fnmatch
import posixpath
import re
import shlex
import stat as statmod

import asyncssh
from fastapi import HTTPException

from code_agent.config import settings
from code_agent.db.models import Workspace
from code_agent.tools.paths import TREE_IGNORES, is_ignored, matches_ignore
from code_agent.workspace.ssh_pool import SshAuth, ssh_pool


def _posix_join(root: str, rel: str) -> str:
    raw = (rel or ".").strip() or "."
    if raw.startswith("~"):
        return raw
    if raw.startswith("/"):
        return posixpath.normpath(raw)
    base = root.rstrip("/") or "/"
    return posixpath.normpath(posixpath.join(base, raw))


def _rel_to_root(root: str, absolute: str) -> str:
    root_n = posixpath.normpath(root.rstrip("/") or "/")
    abs_n = posixpath.normpath(absolute)
    if abs_n == root_n:
        return ""
    prefix = root_n if root_n.endswith("/") else root_n + "/"
    if abs_n.startswith(prefix):
        return abs_n[len(prefix) :]
    return abs_n


class SshWorkspaceBackend:
    kind = "ssh"

    def __init__(self, ws: Workspace, auth: SshAuth, conn_key: str) -> None:
        self._ws = ws
        self._auth = auth
        self._conn_key = conn_key
        self.root_path = ws.root_path

    @classmethod
    async def open(cls, ws: Workspace) -> SshWorkspaceBackend:
        host = getattr(ws, "ssh_host", None) or ""
        user = getattr(ws, "ssh_user", None) or ""
        if not host or not user:
            raise HTTPException(
                status_code=400,
                detail={"code": "ssh.incomplete", "message": "SSH workspace missing host/user"},
            )
        auth = SshAuth.from_workspace_fields(
            host=host,
            port=int(getattr(ws, "ssh_port", None) or 22),
            username=user,
            secret_blob=getattr(ws, "ssh_secret", None) or "",
        )
        key = str(ws.id)
        await ssh_pool.connect(key, auth)
        return cls(ws, auth, key)

    @classmethod
    async def open_ephemeral(cls, auth: SshAuth, root_path: str) -> SshWorkspaceBackend:
        class _Ephemeral:
            id = f"ephemeral:{auth.fingerprint()}"
            ignore_globs: list = []
            kind = "ssh"
            ssh_host = auth.host
            ssh_port = auth.port
            ssh_user = auth.username
            ssh_secret = ""

        ws = _Ephemeral()
        ws.root_path = root_path  # type: ignore[attr-defined]
        key = f"ephemeral:{auth.fingerprint()}"
        await ssh_pool.connect(key, auth)
        backend = cls(ws, auth, key)  # type: ignore[arg-type]
        backend.root_path = root_path
        return backend

    async def _conn(self) -> asyncssh.SSHClientConnection:
        return await ssh_pool.connect(self._conn_key, self._auth)

    async def _sftp(self) -> asyncssh.SFTPClient:
        return await ssh_pool.sftp(self._conn_key, self._auth)

    async def _abs(self, rel: str) -> str:
        path = _posix_join(self.root_path, rel)
        if path.startswith("~"):
            conn = await self._conn()
            result = await conn.run(f"printf %s {shlex.quote(path)}", check=False)
            expanded = (result.stdout or "").strip()
            if expanded:
                return expanded
        return path

    async def list_dir(self, rel: str = "", extra_ignores: list[str] | None = None) -> list[dict]:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            entries = [entry async for entry in sftp.scandir(target)]
        except (OSError, asyncssh.SFTPError) as exc:
            raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": str(exc)}) from exc

        ignores = TREE_IGNORES + list(getattr(self._ws, "ignore_globs", None) or []) + (extra_ignores or [])
        max_children = int(settings.get("workspace.tree_max_children") or 400)
        items: list[dict] = []
        for entry in sorted(
            entries,
            key=lambda e: (str(getattr(e, "filename", "")).startswith("."), str(getattr(e, "filename", "")).lower()),
        ):
            name_s = str(getattr(entry, "filename", "") or "")
            if name_s in {".", ".."}:
                continue
            child = posixpath.join(target, name_s)
            rel_child = _rel_to_root(self.root_path, child) or name_s
            if matches_ignore(rel_child, ignores):
                continue
            attrs = getattr(entry, "attrs", None)
            mode = int(getattr(attrs, "permissions", 0) or 0) if attrs is not None else 0
            if mode:
                is_dir = bool(statmod.S_ISDIR(mode))
                size = int(getattr(attrs, "size", 0) or 0) if not is_dir else None
                mtime_raw = getattr(attrs, "mtime", None)
            else:
                # Fallback when server omits attrs in directory listing
                try:
                    st = await sftp.stat(child)
                    mode = int(getattr(st, "permissions", 0) or 0)
                    is_dir = bool(mode and statmod.S_ISDIR(mode))
                    size = int(getattr(st, "size", 0) or 0) if not is_dir else None
                    mtime_raw = getattr(st, "mtime", None)
                except Exception:
                    is_dir = False
                    size = None
                    mtime_raw = None
            mtime = int(mtime_raw) if mtime_raw is not None else None
            items.append(
                {"name": name_s, "path": rel_child, "is_dir": is_dir, "size": size, "mtime": mtime}
            )
            if len(items) >= max_children:
                break
        return items

    async def read_bytes(self, rel: str, max_bytes: int | None = None) -> bytes:
        sftp = await self._sftp()
        target = await self._abs(rel)
        limit = max_bytes or int(settings.get("workspace.max_file_bytes") or 1048576)
        try:
            attrs = await sftp.stat(target)
            size = int(getattr(attrs, "size", 0) or 0)
            if size > limit:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "file.too_large", "message": f"File exceeds {limit} bytes"},
                )
            async with sftp.open(target, "rb") as fh:
                data = await fh.read(limit + 1)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": str(exc)}) from exc
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        if len(data) > limit:
            raise HTTPException(
                status_code=400,
                detail={"code": "file.too_large", "message": f"File exceeds {limit} bytes"},
            )
        return bytes(data)

    async def read_text(self, rel: str, max_bytes: int | None = None) -> str:
        data = await self.read_bytes(rel, max_bytes=max_bytes)
        if b"\x00" in data[:4096]:
            raise HTTPException(status_code=400, detail={"code": "file.binary", "message": "Binary file"})
        return data.decode("utf-8", errors="replace")

    async def write_text(self, rel: str, content: str) -> None:
        await self.write_bytes(rel, content.encode("utf-8"))

    async def write_bytes(self, rel: str, content: bytes) -> None:
        sftp = await self._sftp()
        target = await self._abs(rel)
        parent = posixpath.dirname(target)
        if parent and parent != "/":
            try:
                await sftp.makedirs(parent)
            except Exception:
                pass
        async with sftp.open(target, "wb") as fh:
            await fh.write(content)

    async def mkdir(self, rel: str) -> None:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            await sftp.makedirs(target)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"code": "path.invalid", "message": str(exc)}) from exc

    async def create_file(self, rel: str) -> None:
        await self.write_text(rel, "")

    async def rename(self, src: str, dest: str) -> None:
        sftp = await self._sftp()
        sp = await self._abs(src)
        dp = await self._abs(dest)
        parent = posixpath.dirname(dp)
        if parent and parent != "/":
            try:
                await sftp.makedirs(parent)
            except Exception:
                pass
        await sftp.rename(sp, dp)

    async def copy(self, src: str, dest: str) -> None:
        if not await self.exists(src):
            raise HTTPException(status_code=404, detail={"code": "path.not_found"})
        if await self.exists(dest):
            raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
        sp = await self._abs(src)
        dp = await self._abs(dest)
        parent = posixpath.dirname(dp)
        if parent and parent != "/":
            sftp = await self._sftp()
            try:
                await sftp.makedirs(parent)
            except Exception:
                pass
        # Prefer remote cp so directories recurse with permissions preserved.
        code, _out, err = await self.run_command(
            f"cp -a -- {shlex.quote(sp)} {shlex.quote(dp)}",
            cwd=".",
            timeout=300,
        )
        if code != 0:
            raise HTTPException(
                status_code=400,
                detail={"code": "copy.failed", "message": (err or "copy failed").strip()[:500]},
            )

    async def delete(self, rel: str) -> None:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            attrs = await sftp.stat(target)
            mode = int(getattr(attrs, "permissions", 0) or 0)
            if mode and statmod.S_ISDIR(mode):
                await sftp.rmtree(target)
            else:
                await sftp.remove(target)
        except Exception as exc:
            raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": str(exc)}) from exc

    async def exists(self, rel: str = ".") -> bool:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            await sftp.stat(target)
            return True
        except Exception:
            return False

    async def is_dir(self, rel: str = ".") -> bool:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            attrs = await sftp.stat(target)
            mode = int(getattr(attrs, "permissions", 0) or 0)
            return bool(mode and statmod.S_ISDIR(mode))
        except Exception:
            return False

    async def is_file(self, rel: str) -> bool:
        sftp = await self._sftp()
        target = await self._abs(rel)
        try:
            attrs = await sftp.stat(target)
            mode = int(getattr(attrs, "permissions", 0) or 0)
            return bool(mode and statmod.S_ISREG(mode))
        except Exception:
            return False

    async def walk_files(
        self,
        extra_ignores: list[str] | None = None,
        limit: int = 5000,
        root_rel: str = "",
    ) -> list[tuple[str, str]]:
        sftp = await self._sftp()
        ignores = list(getattr(self._ws, "ignore_globs", None) or []) + (extra_ignores or [])
        out: list[tuple[str, str]] = []
        start_rel = (root_rel or "").strip().replace("\\", "/").strip("/")

        async def _walk(dir_abs: str, rel_dir: str) -> None:
            if len(out) >= limit:
                return
            try:
                names = await sftp.listdir(dir_abs)
            except Exception:
                return
            for name in names:
                name_s = str(name)
                if name_s in {".", ".."}:
                    continue
                child_abs = posixpath.join(dir_abs, name_s)
                child_rel = f"{rel_dir}/{name_s}".lstrip("/") if rel_dir else name_s
                if is_ignored(child_rel, ignores):
                    continue
                try:
                    attrs = await sftp.stat(child_abs)
                    mode = int(getattr(attrs, "permissions", 0) or 0)
                    if mode and statmod.S_ISDIR(mode):
                        await _walk(child_abs, child_rel)
                    elif mode and statmod.S_ISREG(mode):
                        out.append((child_rel, child_abs))
                        if len(out) >= limit:
                            return
                except Exception:
                    continue

        await _walk(await self._abs(start_rel or "."), start_rel)
        return out

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
        q = (query or "").strip()
        if not q:
            return []
        limit = max_hits or 80
        conn = await self._conn()
        rg_check = await conn.run("command -v rg", check=False)
        if (rg_check.stdout or "").strip():
            cmd = ["rg", "-n", "--hidden", "--no-heading", "-m", "50", "-g", "!node_modules", "-g", "!.git"]
            if not case_sensitive:
                cmd.append("-i")
            if not regex:
                cmd.append("-F")
            for pat in include or []:
                cmd.extend(["-g", pat])
            for pat in exclude or []:
                cmd.extend(["-g", f"!{pat}"])
            cmd.extend([q, self.root_path])
            remote = " ".join(shlex.quote(c) for c in cmd)
            result = await conn.run(remote, check=False)
            hits: list[dict] = []
            for line in (result.stdout or "").splitlines():
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                abs_path, line_no, text = parts[0], parts[1], parts[2]
                rel = _rel_to_root(self.root_path, abs_path)
                hits.append({"path": rel, "line": int(line_no) if line_no.isdigit() else 0, "text": text[:240]})
                if len(hits) >= limit:
                    break
            return hits

        flags = 0 if case_sensitive else re.IGNORECASE
        cre = re.compile(q if regex else re.escape(q), flags)
        hits: list[dict] = []
        files = await self.walk_files(limit=2000)
        for rel, _abs in files:
            if include and not any(fnmatch.fnmatch(rel, p) for p in include):
                continue
            if exclude and any(fnmatch.fnmatch(rel, p) for p in exclude):
                continue
            try:
                text = await self.read_text(rel, max_bytes=256_000)
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if cre.search(line):
                    hits.append({"path": rel, "line": i, "text": line[:240]})
                    if len(hits) >= limit:
                        return hits
        return hits

    async def run_command(
        self, command: str, *, cwd: str = ".", timeout: int = 90
    ) -> tuple[int, str, str]:
        conn = await self._conn()
        work = await self._abs(cwd)
        remote = f"cd {shlex.quote(work)} && {command}"
        try:
            result = await asyncio.wait_for(conn.run(remote, check=False), timeout=timeout)
        except TimeoutError:
            return 124, "", f"command timed out after {timeout}s"
        return int(result.exit_status or 0), result.stdout or "", result.stderr or ""

    async def close(self) -> None:
        await ssh_pool.drop(self._conn_key)
