from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace, WorkspaceMemory

router = APIRouter(prefix="/api/workspaces", tags=["memories"])


class MemoryIn(BaseModel):
    kind: str = "decision"
    subject: str
    content: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class MemoryPatch(BaseModel):
    kind: str | None = None
    subject: str | None = None
    content: dict | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    enabled: bool | None = None


def _source_flags(source: dict | None) -> dict:
    src = source if isinstance(source, dict) else {}
    return {
        "pinned": bool(src.get("pinned")),
        "enabled": src.get("enabled", True) is not False,
    }


def _row(r: WorkspaceMemory) -> dict:
    flags = _source_flags(r.source)
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id),
        "kind": r.kind,
        "subject": r.subject,
        "content": r.content,
        "tags": r.tags or [],
        "source": r.source or {},
        "pinned": flags["pinned"],
        "enabled": flags["enabled"],
        "confidence": r.confidence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/{workspace_id}/memories")
async def list_memories(workspace_id: str):
    if not await Workspace.get_or_none(id=workspace_id):
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    rows = await WorkspaceMemory.filter(workspace_id=workspace_id, superseded_by__isnull=True).order_by(
        "-updated_at"
    )
    return {"memories": [_row(r) for r in rows]}


@router.post("/{workspace_id}/memories")
async def create_memory(workspace_id: str, body: MemoryIn):
    if not await Workspace.get_or_none(id=workspace_id):
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    row = await WorkspaceMemory.create(
        workspace_id=workspace_id,
        kind=body.kind,
        subject=body.subject[:200],
        content=body.content,
        tags=body.tags,
        source={"manual": True},
    )
    return _row(row)


@router.patch("/{workspace_id}/memories/{memory_id}")
async def update_memory(workspace_id: str, memory_id: str, body: MemoryPatch):
    row = await WorkspaceMemory.get_or_none(id=memory_id, workspace_id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "memory.not_found"})
    if body.kind is not None:
        row.kind = body.kind
    if body.subject is not None:
        row.subject = body.subject[:200]
    if body.content is not None:
        row.content = body.content
    if body.tags is not None:
        row.tags = body.tags
    if body.pinned is not None or body.enabled is not None:
        src = dict(row.source or {}) if isinstance(row.source, dict) else {}
        if body.pinned is not None:
            src["pinned"] = bool(body.pinned)
        if body.enabled is not None:
            src["enabled"] = bool(body.enabled)
        row.source = src
    await row.save()
    return _row(row)


@router.delete("/{workspace_id}/memories/{memory_id}")
async def delete_memory(workspace_id: str, memory_id: str):
    row = await WorkspaceMemory.get_or_none(id=memory_id, workspace_id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "memory.not_found"})
    await row.delete()
    return {"ok": True}


class RulePatch(BaseModel):
    path: str
    enabled: bool | None = None
    pinned: bool | None = None


async def _workspace_fs(workspace_id: str):
    ws = await Workspace.get_or_none(id=workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    from code_agent.workspace.backend import get_workspace_backend

    return ws, await get_workspace_backend(ws)


@router.get("/{workspace_id}/rules")
async def list_rules(workspace_id: str):
    from code_agent.agent.rules import list_workspace_rules

    _ws, fs = await _workspace_fs(workspace_id)
    try:
        rules = await list_workspace_rules(fs)
    finally:
        close = getattr(fs, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass
    return {
        "rules": rules,
        "priority": [
            "user",
            "workspace_rules",
            "pinned_memory",
            "other_memory",
        ],
    }


@router.patch("/{workspace_id}/rules")
async def patch_rule(workspace_id: str, body: RulePatch):
    from code_agent.agent.rules import patch_workspace_rule

    _ws, fs = await _workspace_fs(workspace_id)
    try:
        item = await patch_workspace_rule(fs, body.path, enabled=body.enabled, pinned=body.pinned)
    finally:
        close = getattr(fs, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass
    return item
