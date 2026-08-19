from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from code_agent.config import settings
from code_agent.db.models import TerminalSession, Workspace
from code_agent.terminal.pty_manager import create_terminal, pty_manager

router = APIRouter(prefix="/api/terminals", tags=["terminals"])


class TerminalIn(BaseModel):
    workspace_id: str
    title: str | None = None


@router.get("")
async def list_terminals(workspace_id: str):
    rows = await TerminalSession.filter(workspace_id=workspace_id).order_by("-created_at")
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "cwd": r.cwd,
            "alive": bool(pty_manager.get(str(r.id)) and pty_manager.get(str(r.id)).alive),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("")
async def new_terminal(body: TerminalIn):
    ws = await Workspace.get_or_none(id=body.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    row = await create_terminal(body.workspace_id, body.title)
    return {"id": str(row.id), "title": row.title, "cwd": row.cwd, "alive": True}


class TerminalRenameIn(BaseModel):
    title: str


@router.patch("/{terminal_id}")
async def rename_terminal(terminal_id: str, body: TerminalRenameIn):
    row = await TerminalSession.get_or_none(id=terminal_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "terminal.not_found"})
    row.title = body.title.strip() or row.title
    await row.save(update_fields=["title"])
    return {"id": str(row.id), "title": row.title}


@router.delete("/{terminal_id}")
async def kill_terminal(terminal_id: str):
    row = await TerminalSession.get_or_none(id=terminal_id)
    pty_manager.drop(terminal_id)
    if row:
        await row.delete()
    return {"ok": True}


@router.websocket("/{terminal_id}/ws")
async def terminal_ws(websocket: WebSocket, terminal_id: str):
    await websocket.accept()
    row = await TerminalSession.get_or_none(id=terminal_id)
    if not row:
        await websocket.close(code=4404)
        return
    cols = int(settings.get("terminal.default_cols") or 120)
    rows = int(settings.get("terminal.default_rows") or 32)
    handle = pty_manager.attach(terminal_id, row.cwd, cols, rows)
    handle.subscribers.append(websocket)
    if handle.buffer:
        await websocket.send_bytes(bytes(handle.buffer))
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            text = message.get("text")
            if data:
                handle.write(data)
                continue
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    handle.write(text.encode())
                    continue
                if payload.get("type") == "resize":
                    handle.resize(int(payload.get("cols") or cols), int(payload.get("rows") or rows))
                elif payload.get("type") == "input":
                    handle.write(str(payload.get("data") or "").encode())
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in handle.subscribers:
            handle.subscribers.remove(websocket)
