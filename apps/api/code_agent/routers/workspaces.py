from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.policy.engine import is_protected
from code_agent.tools.paths import list_dir, read_text_file, resolve_in_workspace, workspace_root

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceIn(BaseModel):
    name: str | None = None
    root_path: str
    ignore_globs: list[str] = Field(default_factory=list)


class FilePut(BaseModel):
    content: str


class EntryCreate(BaseModel):
    path: str
    kind: str = "file"


class EntryRename(BaseModel):
    path: str
    new_path: str


@router.get("")
async def list_workspaces():
    rows = await Workspace.all().order_by("-last_opened_at")
    return [_ws(r) for r in rows]


@router.post("")
async def add_workspace(body: WorkspaceIn):
    root = Path(body.root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail={"code": "workspace.invalid", "message": "Directory does not exist"})
    row = await Workspace.create(
        name=body.name or root.name,
        root_path=str(root),
        ignore_globs=body.ignore_globs,
    )
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


@router.get("/{workspace_id}/file")
async def get_file(workspace_id: str, path: str):
    ws = await _get_ws(workspace_id)
    file_path = resolve_in_workspace(ws.root_path, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "path.not_found"})
    return {"path": path, "content": read_text_file(file_path)}


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
        if child.name.startswith(".") and child.name not in {".code-agent"}:
            continue
        items.append({"name": child.name, "path": str(child), "is_dir": child.is_dir()})
        if len(items) >= 400:
            break
    return {"path": str(p), "parent": str(p.parent), "items": items}


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
