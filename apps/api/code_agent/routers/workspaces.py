from __future__ import annotations

import mimetypes
import os
import posixpath
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from code_agent.async_io import run_sync
from code_agent.db.models import Workspace
from code_agent.policy.engine import is_protected
from code_agent.tools.paths import replace_file_contents, split_patterns, workspace_root
from code_agent.workspace.backend import get_workspace_backend, workspace_is_ssh
from code_agent.workspace.ssh import SshWorkspaceBackend
from code_agent.workspace.ssh_pool import SshAuth

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

RAW_FILE_MAX_BYTES = 80 * 1024 * 1024
UPLOAD_MAX_BYTES = 80 * 1024 * 1024
ARCHIVE_MAX_FILES = 5000
ARCHIVE_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
ARCHIVE_MAX_FILE_BYTES = RAW_FILE_MAX_BYTES


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 5987-safe Content-Disposition (non-ASCII filenames break latin-1 headers)."""
    name = (filename or "download").replace("\\", "_").replace('"', "")
    encoded = quote(name)
    if encoded != name:
        ascii_fallback = "download"
        return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=utf-8''{encoded}"
    return f'{disposition}; filename="{name}"'

def _normalize_root_path(raw: str) -> str:
    try:
        return str(Path(raw).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        try:
            return str(Path(raw).expanduser())
        except (OSError, RuntimeError, ValueError):
            return str(raw or "")


def _workspace_dedupe_key(row: Workspace) -> str:
    kind = str(getattr(row, "kind", None) or "local").lower()
    if kind == "ssh":
        host = getattr(row, "ssh_host", "") or ""
        port = int(getattr(row, "ssh_port", None) or 22)
        user = getattr(row, "ssh_user", "") or ""
        return f"ssh://{user}@{host}:{port}{row.root_path}"
    try:
        return _normalize_root_path(row.root_path)
    except (OSError, RuntimeError, ValueError):
        return row.root_path


async def _find_workspace_by_key(key: str) -> Workspace | None:
    for row in await Workspace.all():
        if _workspace_dedupe_key(row) == key:
            return row
    return None


def _dedupe_workspaces(rows: list[Workspace]) -> list[Workspace]:
    seen: set[str] = set()
    out: list[Workspace] = []
    for row in rows:
        key = _workspace_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


class WorkspaceIn(BaseModel):
    name: str | None = None
    root_path: str
    ignore_globs: list[str] = Field(default_factory=list)
    kind: Literal["local", "ssh"] = "local"
    ssh_display_name: str | None = None
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_user: str | None = None
    ssh_password: str | None = None
    ssh_private_key: str | None = None
    ssh_passphrase: str | None = None
    reuse_ssh_from: str | None = None


class WorkspaceUpdateIn(BaseModel):
    name: str | None = None
    root_path: str | None = None
    ssh_display_name: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_user: str | None = None
    ssh_password: str | None = None
    ssh_private_key: str | None = None
    ssh_passphrase: str | None = None


class SshBrowseIn(BaseModel):
    host: str = ""
    port: int = 22
    username: str = ""
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None
    path: str = "~"
    workspace_id: str | None = None


class FilePut(BaseModel):
    content: str


class SearchReplaceIn(BaseModel):
    q: str
    replacement: str = ""
    include: str = ""
    exclude: str = ""
    case_sensitive: bool = False


class EntryCreate(BaseModel):
    path: str
    kind: str = "file"


class EntryRename(BaseModel):
    path: str
    new_path: str


class EntryCopy(BaseModel):
    path: str
    new_path: str


class MkdirIn(BaseModel):
    parent: str
    name: str


@router.get("")
async def list_workspaces():
    rows = await Workspace.all().order_by("-last_opened_at", "-created_at")
    return [_ws(r) for r in _dedupe_workspaces(rows)]


@router.post("/ssh/browse")
async def ssh_browse(body: SshBrowseIn):
    auth: SshAuth
    if body.workspace_id:
        src = await _get_ws(body.workspace_id)
        if not workspace_is_ssh(src):
            raise HTTPException(status_code=400, detail={"code": "ssh.incomplete", "message": "workspace is not SSH"})
        auth = SshAuth.from_workspace_fields(
            host=(body.host or src.ssh_host or "").strip() or (src.ssh_host or ""),
            port=int(body.port or src.ssh_port or 22),
            username=(body.username or src.ssh_user or "").strip() or (src.ssh_user or ""),
            secret_blob=getattr(src, "ssh_secret", None) or "",
        )
        # allow overriding password/key if provided
        if body.password:
            auth.password = body.password
        if body.private_key:
            auth.private_key = body.private_key
            auth.passphrase = body.passphrase
    else:
        auth = SshAuth(
            host=body.host.strip(),
            port=int(body.port or 22),
            username=body.username.strip(),
            password=body.password,
            private_key=body.private_key,
            passphrase=body.passphrase,
        )
    if not auth.host or not auth.username:
        raise HTTPException(status_code=400, detail={"code": "ssh.incomplete", "message": "host/username required"})
    if not auth.password and not auth.private_key:
        raise HTTPException(
            status_code=400,
            detail={"code": "ssh.auth", "message": "Provide password or private key"},
        )
    raw = (body.path or "~").strip() or "~"
    try:
        backend = await SshWorkspaceBackend.open_ephemeral(auth, root_path="/")
        if raw in {"", ".", "__roots__"}:
            # remote roots: / + home
            conn = await backend._conn()
            home = (await conn.run('printf %s "$HOME"', check=False)).stdout or ""
            home = home.strip() or "/root"
            items = [
                {"name": "/", "path": "/", "is_dir": True},
                {"name": "Home", "path": home, "is_dir": True},
            ]
            return {"path": "", "parent": "", "items": items, "ok": True}
        if raw.startswith("~"):
            conn = await backend._conn()
            home = (await conn.run('printf %s "$HOME"', check=False)).stdout or ""
            home = home.strip() or "/root"
            raw = home if raw == "~" else posixpath.join(home, raw[2:].lstrip("/"))
        backend.root_path = raw if raw == "/" else posixpath.dirname(raw.rstrip("/")) or "/"
        # list the requested directory itself
        list_root = raw
        if not await backend.exists(list_root if list_root.startswith("/") else f"/{list_root}"):
            # exists() resolves against backend.root_path — set root to /
            backend.root_path = "/"
            if not await backend.is_dir(list_root):
                raise HTTPException(status_code=404, detail={"code": "path.not_found"})
        backend.root_path = list_root
        items = await backend.list_dir(".")
        # rewrite paths to absolute for picker
        abs_items = []
        for item in items:
            abs_path = posixpath.join(list_root, item["name"]) if list_root != "/" else f"/{item['name']}"
            abs_items.append({**item, "path": abs_path})
        parent = "" if list_root in {"/", ""} else posixpath.dirname(list_root.rstrip("/")) or "/"
        if parent == list_root:
            parent = ""
        return {"path": list_root, "parent": parent, "items": abs_items, "ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "ssh.connect_failed", "message": str(exc)},
        ) from exc


@router.post("")
async def add_workspace(body: WorkspaceIn):
    kind = (body.kind or "local").lower()
    if kind == "ssh":
        return await _add_ssh_workspace(body)

    root = Path(body.root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail={"code": "workspace.invalid", "message": "Directory does not exist"})
    key = _normalize_root_path(str(root))
    existing = await _find_workspace_by_key(key)
    if existing and not workspace_is_ssh(existing):
        await existing.save()
        plugins = await _activate_workspace_plugins(existing)
        return {**_ws(existing), "plugins": plugins}
    row = await Workspace.create(
        name=body.name or root.name,
        root_path=str(root),
        ignore_globs=body.ignore_globs,
        kind="local",
    )
    plugins = await _activate_workspace_plugins(row)
    return {**_ws(row), "plugins": plugins}


async def _add_ssh_workspace(body: WorkspaceIn):
    host = (body.ssh_host or "").strip()
    user = (body.ssh_user or "").strip()
    root = (body.root_path or "").strip()
    if not host or not user or not root:
        raise HTTPException(status_code=400, detail={"code": "ssh.incomplete", "message": "host/user/root_path required"})

    reuse_id = (body.reuse_ssh_from or "").strip()
    reused: Workspace | None = None
    if reuse_id:
        reused = await _get_ws(reuse_id)
        if not workspace_is_ssh(reused):
            raise HTTPException(status_code=400, detail={"code": "ssh.incomplete", "message": "reuse source is not SSH"})

    if not body.ssh_password and not body.ssh_private_key and not reused:
        raise HTTPException(status_code=400, detail={"code": "ssh.auth", "message": "Provide password or private key"})

    if body.ssh_password or body.ssh_private_key:
        auth = SshAuth(
            host=host,
            port=int(body.ssh_port or 22),
            username=user,
            password=body.ssh_password,
            private_key=body.ssh_private_key,
            passphrase=body.ssh_passphrase,
        )
        secret = auth.to_secret_blob()
    else:
        assert reused is not None
        auth = SshAuth.from_workspace_fields(
            host=host,
            port=int(body.ssh_port or 22),
            username=user,
            secret_blob=getattr(reused, "ssh_secret", None) or "",
        )
        if not auth.password and not auth.private_key:
            raise HTTPException(status_code=400, detail={"code": "ssh.auth", "message": "Provide password or private key"})
        secret = auth.to_secret_blob()

    # Expand ~ on remote
    backend = await SshWorkspaceBackend.open_ephemeral(auth, root_path="/")
    if root.startswith("~"):
        conn = await backend._conn()
        home = (await conn.run('printf %s "$HOME"', check=False)).stdout or ""
        home = home.strip() or "/root"
        root = home if root == "~" else posixpath.join(home, root[2:].lstrip("/"))
    backend.root_path = "/"
    if not await backend.is_dir(root):
        raise HTTPException(status_code=400, detail={"code": "workspace.invalid", "message": "Remote directory does not exist"})

    key = f"ssh://{user}@{host}:{int(body.ssh_port or 22)}{root}"
    existing = await _find_workspace_by_key(key)
    display_name = (body.ssh_display_name or "").strip()[:120] or None
    if existing and workspace_is_ssh(existing):
        existing.ssh_secret = secret
        existing.root_path = root
        existing.name = body.name or existing.name or posixpath.basename(root.rstrip("/")) or root
        if body.ssh_display_name is not None:
            existing.ssh_display_name = display_name
        await existing.save()
        return {**_ws(existing), "plugins": []}

    row = await Workspace.create(
        name=body.name or posixpath.basename(root.rstrip("/")) or root,
        root_path=root,
        ignore_globs=body.ignore_globs,
        kind="ssh",
        ssh_host=host,
        ssh_port=int(body.ssh_port or 22),
        ssh_user=user,
        ssh_secret=secret,
        ssh_display_name=display_name,
    )
    # warm connection pool under workspace id
    await get_workspace_backend(row)
    return {**_ws(row), "plugins": []}


@router.post("/{workspace_id}/open")
async def open_workspace(workspace_id: str):
    row = await _get_ws(workspace_id)
    await row.save()
    if workspace_is_ssh(row):
        await get_workspace_backend(row)
    plugins = await _activate_workspace_plugins(row)
    return {**_ws(row), "plugins": plugins}


@router.post("/{workspace_id}/plugins/reload")
async def reload_workspace_plugins(workspace_id: str):
    row = await _get_ws(workspace_id)
    plugins = await _activate_workspace_plugins(row)
    return {"ok": True, **plugins}


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: str, body: WorkspaceUpdateIn):
    row = await _get_ws(workspace_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail={"code": "workspace.invalid", "message": "名称不能为空"})
        row.name = name[:200]

    if workspace_is_ssh(row):
        from code_agent.workspace.ssh_pool import ssh_pool

        if body.ssh_display_name is not None:
            label = body.ssh_display_name.strip()
            row.ssh_display_name = label[:120] if label else None

        host = (body.ssh_host if body.ssh_host is not None else row.ssh_host or "").strip()
        user = (body.ssh_user if body.ssh_user is not None else row.ssh_user or "").strip()
        port = int(body.ssh_port if body.ssh_port is not None else (row.ssh_port or 22))
        root = (body.root_path if body.root_path is not None else row.root_path or "").strip()
        if not host or not user or not root:
            raise HTTPException(
                status_code=400,
                detail={"code": "ssh.incomplete", "message": "host/user/root_path required"},
            )

        cred_touched = any(
            field not in (None, "")
            for field in (body.ssh_password, body.ssh_private_key, body.ssh_passphrase)
        )
        conn_changed = (
            host != (row.ssh_host or "")
            or user != (row.ssh_user or "")
            or port != int(row.ssh_port or 22)
            or root != (row.root_path or "")
            or cred_touched
        )

        if not conn_changed:
            await row.save()
            return _ws(row)

        existing_auth = SshAuth.from_workspace_fields(
            host=row.ssh_host or host,
            port=int(row.ssh_port or 22),
            username=row.ssh_user or user,
            secret_blob=getattr(row, "ssh_secret", None) or "",
        )
        password = body.ssh_password if body.ssh_password not in (None, "") else existing_auth.password
        private_key = body.ssh_private_key if body.ssh_private_key not in (None, "") else existing_auth.private_key
        passphrase = body.ssh_passphrase if body.ssh_passphrase not in (None, "") else existing_auth.passphrase
        if body.ssh_password not in (None, "") and body.ssh_private_key in (None, ""):
            # switching to password auth
            if body.ssh_private_key == "":
                private_key = None
                passphrase = body.ssh_passphrase or None
        if body.ssh_private_key not in (None, "") and body.ssh_password in (None, ""):
            if body.ssh_password == "":
                password = None

        if not password and not private_key:
            raise HTTPException(
                status_code=400,
                detail={"code": "ssh.auth", "message": "Provide password or private key"},
            )

        auth = SshAuth(
            host=host,
            port=port,
            username=user,
            password=password,
            private_key=private_key,
            passphrase=passphrase,
        )
        try:
            backend = await SshWorkspaceBackend.open_ephemeral(auth, root_path="/")
            if root.startswith("~"):
                conn = await backend._conn()
                home = (await conn.run('printf %s "$HOME"', check=False)).stdout or ""
                home = home.strip() or "/root"
                root = home if root == "~" else posixpath.join(home, root[2:].lstrip("/"))
            backend.root_path = "/"
            if not await backend.is_dir(root):
                raise HTTPException(
                    status_code=400,
                    detail={"code": "workspace.invalid", "message": "Remote directory does not exist"},
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "ssh.connect_failed", "message": str(exc)},
            ) from exc

        row.ssh_host = host
        row.ssh_port = port
        row.ssh_user = user
        row.root_path = root
        row.ssh_secret = auth.to_secret_blob()
        await row.save()
        await ssh_pool.drop(str(row.id))
        await get_workspace_backend(row)
        return _ws(row)

    if body.root_path is not None:
        root = Path(body.root_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise HTTPException(
                status_code=400,
                detail={"code": "workspace.invalid", "message": "Directory does not exist"},
            )
        row.root_path = str(root)
    await row.save()
    return _ws(row)


@router.delete("/{workspace_id}")
async def remove_workspace(workspace_id: str):
    row = await Workspace.get_or_none(id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    from code_agent.plugins.loader import active_workspace_root, unload_workspace_plugins
    from code_agent.workspace.mirror import clear_mirror, mirror_root
    from code_agent.workspace.ssh_pool import ssh_pool

    removed_plugins: list[str] = []
    if workspace_is_ssh(row):
        mirrored = str(mirror_root(str(row.id)))
        if active_workspace_root() == mirrored:
            removed_plugins = unload_workspace_plugins()
        await ssh_pool.drop(str(row.id))
        try:
            from code_agent.ports.ssh_tunnel import ssh_forwards

            await ssh_forwards.drop_workspace(str(row.id))
        except Exception:
            pass
        clear_mirror(str(row.id))
    else:
        try:
            normalized = _normalize_root_path(row.root_path)
        except (OSError, RuntimeError, ValueError):
            normalized = row.root_path
        if active_workspace_root() == normalized:
            removed_plugins = unload_workspace_plugins()
    await row.delete()
    return {"ok": True, "plugins_removed": removed_plugins}


@router.get("/{workspace_id}/tree")
async def tree(workspace_id: str, path: str = ""):
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    items = await backend.list_dir(path)
    return {"items": items}


@router.get("/{workspace_id}/search")
async def search_workspace(
    workspace_id: str,
    q: str = "",
    limit: int = 80,
    include: str = "",
    exclude: str = "",
    case_sensitive: bool = False,
):
    ws = await _get_ws(workspace_id)
    query = (q or "").strip()
    if not query:
        return {"query": query, "hits": []}
    cap = max(1, min(int(limit or 80), 200))
    backend = await get_workspace_backend(ws)
    hits = await backend.search(
        query,
        case_sensitive=case_sensitive,
        include=split_patterns(include),
        exclude=split_patterns(exclude),
        max_hits=cap,
    )
    return {"query": query, "hits": hits}


@router.get("/{workspace_id}/find-files")
async def find_files(workspace_id: str, q: str = "", limit: int = 50):
    """Fuzzy-ish filename / path matcher for Ctrl/Cmd+P quick open."""
    ws = await _get_ws(workspace_id)
    query = (q or "").strip().lower()
    cap = max(1, min(int(limit or 50), 100))
    backend = await get_workspace_backend(ws)
    walked = await backend.walk_files(extra_ignores=ws.ignore_globs, limit=8000)
    files: list[dict[str, str]] = []
    for rel, _abs in walked:
        name = posixpath.basename(rel)
        if query and query not in rel.lower() and query not in name.lower():
            continue
        files.append({"path": rel, "name": name})
    if query:
        files.sort(key=lambda item: (0 if query in item["name"].lower() else 1, len(item["path"]), item["path"]))
    else:
        files.sort(key=lambda item: item["path"])
    return {"query": q, "files": files[:cap]}


@router.post("/{workspace_id}/replace")
async def replace_workspace(workspace_id: str, body: SearchReplaceIn):
    ws = await _get_ws(workspace_id)
    query = (body.q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail={"code": "search.empty", "message": "替换关键词不能为空"})
    if workspace_is_ssh(ws):
        from code_agent.policy.engine import is_protected
        from code_agent.tools.paths import _replace_count, path_in_scope

        backend = await get_workspace_backend(ws)
        includes = split_patterns(body.include)
        excludes = split_patterns(body.exclude)
        files = await backend.walk_files(extra_ignores=ws.ignore_globs, limit=8000)
        items: list[dict] = []
        skipped: list[dict] = []
        total = 0
        for rel, _ in files:
            if not path_in_scope(rel, includes, excludes):
                continue
            if is_protected(rel):
                skipped.append({"path": rel, "reason": "protected"})
                continue
            try:
                text = await backend.read_text(rel)
            except Exception:
                skipped.append({"path": rel, "reason": "unreadable"})
                continue
            next_text, count = _replace_count(text, query, body.replacement, body.case_sensitive)
            if not count or next_text == text:
                continue
            try:
                await backend.write_text(rel, next_text)
            except Exception as err:
                skipped.append({"path": rel, "reason": str(err)})
                continue
            items.append({"path": rel, "count": count})
            total += count
            if len(items) >= 200:
                break
        return {"files": len(items), "replacements": total, "skipped": skipped, "items": items}
    result = await run_sync(
        replace_file_contents,
        ws.root_path,
        query,
        body.replacement,
        extra_ignores=ws.ignore_globs,
        includes=split_patterns(body.include),
        excludes=split_patterns(body.exclude),
        case_sensitive=body.case_sensitive,
    )
    return result


@router.get("/{workspace_id}/file")
async def get_file(workspace_id: str, path: str):
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if not await backend.is_file(path):
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    content = await backend.read_text(path)
    return {"path": path, "content": content}


@router.get("/{workspace_id}/file/raw")
async def get_file_raw(workspace_id: str, path: str, download: bool = False):
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if not await backend.is_file(path):
        raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": "文件不存在"})
    if not workspace_is_ssh(ws):
        from code_agent.tools.paths import resolve_in_workspace

        file_path = resolve_in_workspace(ws.root_path, path)
        size = file_path.stat().st_size
        if size > RAW_FILE_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "file.too_large",
                    "message": f"文件过大（{size} bytes），预览上限 {RAW_FILE_MAX_BYTES} bytes",
                },
            )
        mime, _ = mimetypes.guess_type(str(file_path))
        media_type = mime or "application/octet-stream"
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name,
            content_disposition_type="attachment" if download else "inline",
        )

    data = await backend.read_bytes(path, max_bytes=RAW_FILE_MAX_BYTES)
    mime, _ = mimetypes.guess_type(path)
    media_type = mime or "application/octet-stream"
    filename = posixpath.basename(path) or "download"
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(disposition, filename)},
    )


def _archive_prefix(path: str) -> str:
    rel = (path or "").strip().replace("\\", "/").strip("/")
    if not rel or rel == ".":
        return ""
    if ".." in rel.split("/"):
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})
    return rel


def _arcname_for(rel: str, prefix: str, folder_name: str) -> str:
    if not prefix:
        return rel
    rest = rel[len(prefix) :].lstrip("/")
    return f"{folder_name}/{rest}" if rest else folder_name


@router.get("/{workspace_id}/archive")
async def download_archive(workspace_id: str, path: str = ""):
    """Download a workspace directory as a ZIP archive."""
    prefix = _archive_prefix(path)
    if prefix and is_protected(prefix):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})

    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if prefix:
        if not await backend.exists(prefix):
            raise HTTPException(status_code=404, detail={"code": "path.not_found"})
        if not await backend.is_dir(prefix):
            raise HTTPException(
                status_code=400,
                detail={"code": "path.not_dir", "message": "Archive download requires a directory"},
            )

    folder_name = posixpath.basename(prefix) if prefix else (ws.name or "workspace")
    folder_name = folder_name.replace("\\", "_").replace("/", "_") or "folder"

    walked = await backend.walk_files(
        extra_ignores=ws.ignore_globs,
        limit=ARCHIVE_MAX_FILES + 1,
        root_rel=prefix,
    )
    selected: list[tuple[str, str]] = []
    for rel, abs_or_remote in walked:
        if is_protected(rel):
            continue
        selected.append((rel, abs_or_remote))
        if len(selected) > ARCHIVE_MAX_FILES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "archive.too_many_files",
                    "message": f"Directory has more than {ARCHIVE_MAX_FILES} files",
                },
            )

    tmp = tempfile.NamedTemporaryFile(prefix="ca-archive-", suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()
    total_bytes = 0
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if not selected:
                # Keep empty dirs downloadable.
                zf.writestr(f"{folder_name}/", b"")
            elif not workspace_is_ssh(ws):
                for rel, abs_path in selected:
                    file_path = Path(abs_path)
                    try:
                        size = file_path.stat().st_size
                    except OSError:
                        continue
                    if size > ARCHIVE_MAX_FILE_BYTES:
                        continue
                    total_bytes += size
                    if total_bytes > ARCHIVE_MAX_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "code": "archive.too_large",
                                "message": f"Archive exceeds {ARCHIVE_MAX_UNCOMPRESSED_BYTES} bytes",
                            },
                        )
                    arc = _arcname_for(rel, prefix, folder_name)
                    zf.write(file_path, arcname=arc)
            else:
                for rel, _remote in selected:
                    try:
                        data = await backend.read_bytes(rel, max_bytes=ARCHIVE_MAX_FILE_BYTES + 1)
                    except Exception:
                        continue
                    if len(data) > ARCHIVE_MAX_FILE_BYTES:
                        continue
                    total_bytes += len(data)
                    if total_bytes > ARCHIVE_MAX_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "code": "archive.too_large",
                                "message": f"Archive exceeds {ARCHIVE_MAX_UNCOMPRESSED_BYTES} bytes",
                            },
                        )
                    arc = _arcname_for(rel, prefix, folder_name)
                    zf.writestr(arc, data)
    except HTTPException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    filename = f"{folder_name}.zip"
    return FileResponse(
        path=tmp_path,
        media_type="application/zip",
        filename=filename,
        content_disposition_type="attachment",
        background=BackgroundTask(lambda: os.unlink(tmp_path) if os.path.exists(tmp_path) else None),
    )


@router.put("/{workspace_id}/file")
async def put_file(workspace_id: str, path: str, body: FilePut):
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    await backend.write_text(path, body.content)
    return {"ok": True, "path": path}


@router.post("/{workspace_id}/upload")
async def upload_workspace_file(
    workspace_id: str,
    path: str,
    file: UploadFile = File(...),
):
    """Upload a local file into the workspace (binary-safe)."""
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or rel in {".", ".."} or ".." in rel.split("/"):
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})
    if is_protected(rel):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
    name = posixpath.basename(rel)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})

    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "upload.too_large",
                "message": f"File exceeds {UPLOAD_MAX_BYTES} bytes",
            },
        )

    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    await backend.write_bytes(rel, data)
    return {"ok": True, "path": rel, "size": len(data)}


@router.post("/{workspace_id}/entries")
async def create_entry(workspace_id: str, body: EntryCreate):
    if not body.path.strip() or body.kind not in {"file", "dir"}:
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if await backend.exists(body.path):
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
    if body.kind == "dir":
        await backend.mkdir(body.path)
    else:
        await backend.create_file(body.path)
    return {"ok": True, "path": body.path, "kind": body.kind}


@router.post("/{workspace_id}/rename")
async def rename_entry(workspace_id: str, body: EntryRename):
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if not await backend.exists(body.path):
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if await backend.exists(body.new_path):
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
    await backend.rename(body.path, body.new_path)
    return {"ok": True, "path": body.new_path}


@router.post("/{workspace_id}/copy")
async def copy_entry(workspace_id: str, body: EntryCopy):
    src = (body.path or "").strip()
    dest = (body.new_path or "").strip()
    if not src or not dest or src in {".", "/"} or dest in {".", "/"}:
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})
    if is_protected(src) or is_protected(dest):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
    # Prevent copying a directory into itself / a descendant.
    if dest == src or dest.startswith(f"{src.rstrip('/')}/"):
        raise HTTPException(status_code=400, detail={"code": "path.invalid", "message": "Cannot copy into itself"})
    ws = await _get_ws(workspace_id)
    backend = await get_workspace_backend(ws)
    if not await backend.exists(src):
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if await backend.exists(dest):
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
    await backend.copy(src, dest)
    return {"ok": True, "path": dest}


@router.delete("/{workspace_id}/entries")
async def delete_entry(workspace_id: str, path: str):
    ws = await _get_ws(workspace_id)
    if not path or path in {".", "/"}:
        raise HTTPException(status_code=400, detail={"code": "path.protected", "message": "Cannot delete workspace root"})
    if is_protected(path):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
    backend = await get_workspace_backend(ws)
    if not workspace_is_ssh(ws):
        from code_agent.tools.paths import resolve_in_workspace

        target = resolve_in_workspace(ws.root_path, path)
        root = workspace_root(ws.root_path)
        if target == root:
            raise HTTPException(status_code=400, detail={"code": "path.protected", "message": "Cannot delete workspace root"})
        if is_protected(target.name):
            raise HTTPException(status_code=403, detail={"code": "path.protected"})
    if not await backend.exists(path):
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    await backend.delete(path)
    return {"ok": True}


@router.get("/browse")
async def browse(path: str = "~"):
    raw = (path or "").strip()
    if raw in {"", ".", "__roots__"}:
        return await run_sync(_browse_roots)

    p = Path(raw).expanduser().resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if p.is_file():
        p = p.parent
    items = await run_sync(_browse_dir, p)
    parent = "" if p.parent == p else str(p.parent)
    return {"path": str(p), "parent": parent, "items": items}


@router.post("/mkdir")
async def mkdir(body: MkdirIn):
    parent = Path(body.parent).expanduser().resolve()
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=400, detail={"code": "path.invalid", "message": "上级目录不存在"})
    name = (body.name or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail={"code": "path.invalid", "message": "名称不合法"})
    dest = (parent / name).resolve()
    try:
        dest.relative_to(parent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "path.invalid", "message": "名称不合法"}) from exc
    if dest.exists():
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "已存在同名文件或目录"})
    try:
        await run_sync(dest.mkdir)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "path.denied", "message": "没有权限创建目录"}) from exc
    return {"name": dest.name, "path": str(dest), "parent": str(parent)}


async def _get_ws(workspace_id: str) -> Workspace:
    ws = await Workspace.get_or_none(id=workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    return ws


def _browse_dir(p: Path) -> list[dict]:
    items: list[dict] = []
    try:
        children = list(p.iterdir())
    except PermissionError:
        return items
    for child in sorted(children, key=lambda x: (not x.is_dir(), x.name.lower())):
        items.append({"name": child.name, "path": str(child), "is_dir": child.is_dir()})
        if len(items) >= 400:
            break
    return items


def _browse_roots() -> dict:
    items: list[dict] = []
    if os.name == "nt":
        drives: list[str] = []
        listdrives = getattr(os, "listdrives", None)
        if callable(listdrives):
            drives = list(listdrives())
        else:
            drives = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
        for drive in drives:
            path = drive if drive.endswith(("\\", "/")) else f"{drive}\\"
            label = path.rstrip("\\/") + "\\"
            items.append({"name": label, "path": path, "is_dir": True})
    else:
        items.append({"name": "/", "path": "/", "is_dir": True})
        home = str(Path.home())
        if home and home != "/":
            items.append({"name": "Home", "path": home, "is_dir": True})
    return {"path": "", "parent": "", "items": items}


async def _activate_workspace_plugins(row: Workspace) -> list[dict]:
    from code_agent.plugins.loader import activate_workspace_plugins_for

    result = await activate_workspace_plugins_for(row)
    return result.get("plugins") or []


def _ws(row: Workspace) -> dict:
    kind = str(getattr(row, "kind", None) or "local")
    out = {
        "id": str(row.id),
        "name": row.name,
        "root_path": row.root_path,
        "ignore_globs": row.ignore_globs,
        "kind": kind,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_opened_at": row.last_opened_at.isoformat() if row.last_opened_at else None,
    }
    if kind == "ssh":
        out["ssh_host"] = getattr(row, "ssh_host", None)
        out["ssh_port"] = getattr(row, "ssh_port", None)
        out["ssh_user"] = getattr(row, "ssh_user", None)
        out["ssh_display_name"] = getattr(row, "ssh_display_name", None)
        out["has_ssh_secret"] = bool(getattr(row, "ssh_secret", None))
        out["display_path"] = f"{row.ssh_user}@{row.ssh_host}:{row.root_path}"
    else:
        out["display_path"] = row.root_path
    return out
