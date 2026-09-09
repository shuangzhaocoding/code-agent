from __future__ import annotations

from fastapi import APIRouter, Query

from code_agent.db.models import Workspace
from code_agent.skills.registry import discover_skills, ensure_skills_ready, list_skill_catalog

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(workspace_id: str | None = Query(default=None)):
    ws = None
    if workspace_id:
        ws = await Workspace.get_or_none(id=workspace_id)
        if ws:
            await ensure_skills_ready(ws)
    return list_skill_catalog(ws)


@router.get("/{name}")
async def get_skill(name: str, workspace_id: str | None = Query(default=None)):
    ws = None
    if workspace_id:
        ws = await Workspace.get_or_none(id=workspace_id)
        if ws:
            await ensure_skills_ready(ws)
    for s in discover_skills(ws):
        if s["name"] == name:
            return s
    return {"name": name, "invalid_reason": "not found"}
