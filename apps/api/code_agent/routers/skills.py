from __future__ import annotations

from fastapi import APIRouter, Query

from code_agent.db.models import Workspace
from code_agent.skills.registry import discover_skills, list_skill_catalog

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(workspace_id: str | None = Query(default=None)):
    root = None
    if workspace_id:
        ws = await Workspace.get_or_none(id=workspace_id)
        root = ws.root_path if ws else None
    return list_skill_catalog(root)


@router.get("/{name}")
async def get_skill(name: str, workspace_id: str | None = Query(default=None)):
    root = None
    if workspace_id:
        ws = await Workspace.get_or_none(id=workspace_id)
        root = ws.root_path if ws else None
    for s in discover_skills(root):
        if s["name"] == name:
            return s
    return {"name": name, "invalid_reason": "not found"}
