from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.mcp.bridge import forget_mcp_session, mcp_server_views, probe_mcp_server, refresh_mcp_tools
from code_agent.mcp.config import PRESETS, delete_mcp_server, upsert_mcp_server

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpServerIn(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    origin: str = "workspace"
    workspace_id: str | None = None


async def _root(workspace_id: str | None) -> str | None:
    if not workspace_id:
        return None
    ws = await Workspace.get_or_none(id=workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    return ws.root_path


@router.get("/presets")
async def mcp_presets():
    return {"presets": PRESETS}


@router.get("/servers")
async def list_mcp_servers(workspace_id: str | None = None):
    root = await _root(workspace_id)
    return {"servers": mcp_server_views(root)}


@router.post("/refresh")
async def refresh_mcp(workspace_id: str | None = None):
    root = await _root(workspace_id)
    live = await refresh_mcp_tools(root, persist_sessions=False)
    return {"servers": live}


@router.post("/servers")
async def save_mcp_server(body: McpServerIn):
    root = await _root(body.workspace_id)
    try:
        item = upsert_mcp_server(body.model_dump(), workspace_root=root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "mcp.invalid", "message": str(exc)}) from exc
    await forget_mcp_session(item["name"])
    return item


@router.delete("/servers/{name}")
async def remove_mcp_server(name: str, workspace_id: str | None = None, origin: str = "workspace"):
    root = await _root(workspace_id)
    delete_mcp_server(name, workspace_root=root, origin=origin)
    await forget_mcp_session(name)
    return {"ok": True}


@router.post("/servers/test")
async def test_mcp_server(body: McpServerIn):
    return await probe_mcp_server(body.model_dump())
