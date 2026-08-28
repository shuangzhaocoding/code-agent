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


def _row(r: WorkspaceMemory) -> dict:
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id),
        "kind": r.kind,
        "subject": r.subject,
        "content": r.content,
        "tags": r.tags or [],
        "source": r.source or {},
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
    await row.save()
    return _row(row)


@router.delete("/{workspace_id}/memories/{memory_id}")
async def delete_memory(workspace_id: str, memory_id: str):
    row = await WorkspaceMemory.get_or_none(id=memory_id, workspace_id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "memory.not_found"})
    await row.delete()
    return {"ok": True}
