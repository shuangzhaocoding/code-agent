from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.policy.engine import is_protected
from code_agent.tools.paths import (
    list_dir,
    read_text_file,
    replace_file_contents,
    resolve_in_workspace,
    search_file_contents,
    split_patterns,
    workspace_root,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

# Max size for browser preview of binary / media files
RAW_FILE_MAX_BYTES = 80 * 1024 * 1024


def _normalize_root_path(raw: str) -> str:
    return str(Path(raw).expanduser().resolve())


async def _find_workspace_by_root(root: str) -> Workspace | None:
    target = _normalize_root_path(root)
    for row in await Workspace.all():
        try:
            if _normalize_root_path(row.root_path) == target:
                return row
        except OSError:
            continue
    return None


def _dedupe_workspaces(rows: list[Workspace]) -> list[Workspace]:
    """Keep the most recently opened row per resolved root path."""
    seen: set[str] = set()
    out: list[Workspace] = []
    for row in rows:
        try:
            key = _normalize_root_path(row.root_path)
        except OSError:
            key = row.root_path
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


class WorkspaceIn(BaseModel):
    name: str | None = None
    root_path: str
    ignore_globs: list[str] = Field(default_factory=list)


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


class MkdirIn(BaseModel):
    parent: str
    name: str


@router.get("")
async def list_workspaces():
    rows = await Workspace.all().order_by("-last_opened_at")
    return [_ws(r) for r in _dedupe_workspaces(rows)]


@router.post("")
async def add_workspace(body: WorkspaceIn):
    root = Path(body.root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail={"code": "workspace.invalid", "message": "Directory does not exist"})
    existing = await _find_workspace_by_root(str(root))
    if existing:
        await existing.save()
        return _ws(existing)
    row = await Workspace.create(
        name=body.name or root.name,
        root_path=str(root),
        ignore_globs=body.ignore_globs,
    )
    return _ws(row)


@router.post("/{workspace_id}/open")
async def open_workspace(workspace_id: str):
    row = await _get_ws(workspace_id)
    await row.save()
    return _ws(row)


@router.delete("/{workspace_id}")
async def remove_workspace(workspace_id: str):
    row = await Workspace.get_or_none(id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    await row.delete()
    return {"ok": True}


@router.get("/{workspace_id}/tree")
async def tree(workspace_id: str, path: str = ""):
    ws = await _get_ws(workspace_id)
    return {"items": list_dir(ws.root_path, path, ws.ignore_globs)}


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
    hits = search_file_contents(
        ws.root_path,
        query,
        extra_ignores=ws.ignore_globs,
        limit=cap,
        per_file=50,
        includes=split_patterns(include),
        excludes=split_patterns(exclude),
        case_sensitive=case_sensitive,
    )
    return {"query": query, "hits": hits}


@router.post("/{workspace_id}/replace")
async def replace_workspace(workspace_id: str, body: SearchReplaceIn):
    ws = await _get_ws(workspace_id)
    query = (body.q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail={"code": "search.empty", "message": "替换关键词不能为空"})
    result = replace_file_contents(
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
    file_path = resolve_in_workspace(ws.root_path, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    return {"path": path, "content": read_text_file(file_path)}


@router.get("/{workspace_id}/file/raw")
async def get_file_raw(workspace_id: str, path: str, download: bool = False):
    ws = await _get_ws(workspace_id)
    file_path = resolve_in_workspace(ws.root_path, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": "文件不存在"})
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


@router.put("/{workspace_id}/file")
async def put_file(workspace_id: str, path: str, body: FilePut):
    ws = await _get_ws(workspace_id)
    file_path = resolve_in_workspace(ws.root_path, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")
    return {"ok": True, "path": path}


@router.post("/{workspace_id}/entries")
async def create_entry(workspace_id: str, body: EntryCreate):
    if not body.path.strip() or body.kind not in {"file", "dir"}:
        raise HTTPException(status_code=400, detail={"code": "path.invalid"})
    ws = await _get_ws(workspace_id)
    target = resolve_in_workspace(ws.root_path, body.path)
    if target.exists():
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
    if body.kind == "dir":
        target.mkdir(parents=True, exist_ok=False)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    return {"ok": True, "path": body.path, "kind": body.kind}


@router.post("/{workspace_id}/rename")
async def rename_entry(workspace_id: str, body: EntryRename):
    ws = await _get_ws(workspace_id)
    src = resolve_in_workspace(ws.root_path, body.path)
    dest = resolve_in_workspace(ws.root_path, body.new_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if dest.exists():
        raise HTTPException(status_code=409, detail={"code": "path.exists", "message": "Already exists"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)
    return {"ok": True, "path": body.new_path}


@router.delete("/{workspace_id}/entries")
async def delete_entry(workspace_id: str, path: str):
    ws = await _get_ws(workspace_id)
    target = resolve_in_workspace(ws.root_path, path)
    root = workspace_root(ws.root_path)
    if target == root:
        raise HTTPException(status_code=400, detail={"code": "path.protected", "message": "Cannot delete workspace root"})
    if is_protected(path) or is_protected(target.name):
        raise HTTPException(status_code=403, detail={"code": "path.protected"})
    if not target.exists():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"ok": True}


@router.get("/browse")
async def browse(path: str = "~"):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    if p.is_file():
        p = p.parent
    items = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        items.append({"name": child.name, "path": str(child), "is_dir": child.is_dir()})
        if len(items) >= 400:
            break
    return {"path": str(p), "parent": str(p.parent), "items": items}


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
        dest.mkdir()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "path.denied", "message": "没有权限创建目录"}) from exc
    return {"name": dest.name, "path": str(dest), "parent": str(parent)}


async def _get_ws(workspace_id: str) -> Workspace:
    ws = await Workspace.get_or_none(id=workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    return ws


def _ws(row: Workspace) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "root_path": row.root_path,
        "ignore_globs": row.ignore_globs,
        "last_opened_at": row.last_opened_at.isoformat() if row.last_opened_at else None,
    }
