from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Conversation, Message, Run, Workspace
from code_agent.streaming.run_manager import start_run

router = APIRouter(prefix="/api", tags=["conversations"])


class ConversationIn(BaseModel):
    workspace_id: str
    title: str | None = None
    mode: str = "agent"
    model_id: str | None = None


class MessageIn(BaseModel):
    text: str
    mode: str = "agent"
    model_id: str | None = None
    thinking: bool = False
    references: list[dict] = Field(default_factory=list)


@router.get("/workspaces/{workspace_id}/conversations")
async def list_conversations(workspace_id: str):
    rows = await Conversation.filter(workspace_id=workspace_id, archived=False).order_by("-updated_at")
    return [_conv(r) for r in rows]


@router.post("/conversations")
async def create_conversation(body: ConversationIn):
    ws = await Workspace.get_or_none(id=body.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    row = await Conversation.create(
        workspace_id=body.workspace_id,
        title=body.title or "New chat",
        mode=body.mode,
        model_id=body.model_id,
    )
    return _conv(row)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    row = await Conversation.get_or_none(id=conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})
    messages = await Message.filter(conversation_id=conversation_id).order_by("sort_key")
    run = None
    if row.active_run_id:
        run = await Run.get_or_none(id=row.active_run_id)
    return {
        **_conv(row),
        "messages": [_msg(m) for m in messages],
        "active_run": _run(run) if run else None,
    }


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, body: dict):
    row = await Conversation.get_or_none(id=conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})
    if "title" in body:
        row.title = str(body["title"])[:300]
    if "archived" in body:
        row.archived = bool(body["archived"])
    await row.save()
    return _conv(row)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    row = await Conversation.get_or_none(id=conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})
    await row.delete()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, body: MessageIn):
    row = await Conversation.get_or_none(id=conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})
    if row.active_run_id:
        active = await Run.get_or_none(id=row.active_run_id)
        if active and active.status in {"queued", "running"}:
            raise HTTPException(status_code=409, detail={"code": "run.busy", "message": "A run is already in progress"})
    run = await start_run(
        conversation_id,
        body.text,
        body.mode,
        body.model_id or row.model_id,
        body.references,
        body.thinking,
    )
    return {"run_id": str(run.id), "conversation_id": conversation_id}


def _conv(row: Conversation) -> dict:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "title": row.title,
        "mode": row.mode,
        "model_id": row.model_id,
        "active_run_id": row.active_run_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _msg(row: Message) -> dict:
    return {
        "id": str(row.id),
        "role": row.role,
        "blocks": row.blocks,
        "run_id": row.run_id,
        "sort_key": row.sort_key,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _run(row: Run) -> dict:
    return {
        "id": str(row.id),
        "status": row.status,
        "mode": row.mode,
        "last_event_id": row.last_event_id,
        "last_seq": row.last_seq,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "usage": row.usage_json,
    }
