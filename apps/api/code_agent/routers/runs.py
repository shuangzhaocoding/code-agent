from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel

from code_agent.db.models import Conversation, Run, Workspace
from code_agent.streaming.broker import broker
from code_agent.streaming.run_manager import cancel_run
from code_agent.agent.hitl import resolve_approval
from code_agent.file_checkpoints import get_run_checkpoint, restore_run_files

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/active")
async def list_active_runs(workspace_id: str | None = Query(default=None)):
    """List queued/running runs, optionally scoped to a workspace."""
    q = Run.filter(status__in=["queued", "running"]).order_by("-started_at")
    rows = await q
    if not rows:
        return {"runs": [], "active": 0, "max_concurrent": None}

    from code_agent.streaming.run_capacity import active_run_count, max_concurrent_runs

    conv_ids = list({str(r.conversation_id) for r in rows})
    convs = await Conversation.filter(id__in=conv_ids)
    conv_map = {str(c.id): c for c in convs}

    if workspace_id:
        filtered = []
        for r in rows:
            conv = conv_map.get(str(r.conversation_id))
            if conv and str(conv.workspace_id) == workspace_id:
                filtered.append(r)
        rows = filtered

    ws_ids = list(
        {
            str(conv_map[str(r.conversation_id)].workspace_id)
            for r in rows
            if str(r.conversation_id) in conv_map
        }
    )
    workspaces = await Workspace.filter(id__in=ws_ids) if ws_ids else []
    ws_map = {str(w.id): w for w in workspaces}

    out = []
    for r in rows:
        conv = conv_map.get(str(r.conversation_id))
        ws = ws_map.get(str(conv.workspace_id)) if conv else None
        out.append(
            {
                "run_id": str(r.id),
                "status": r.status,
                "mode": r.mode,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "conversation_id": str(r.conversation_id),
                "conversation_title": conv.title if conv else None,
                "workspace_id": str(conv.workspace_id) if conv else None,
                "workspace_name": ws.name if ws else None,
            }
        )
    return {
        "runs": out,
        "active": active_run_count(),
        "max_concurrent": max_concurrent_runs(),
    }


@router.get("/{run_id}")
async def get_run(run_id: str):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    snapshot = row.model_snapshot or {}
    return {
        "id": str(row.id),
        "status": row.status,
        "mode": row.mode,
        "last_event_id": row.last_event_id,
        "last_seq": row.last_seq,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "usage": row.usage_json,
        "conversation_id": str(row.conversation_id),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "model_snapshot": {
            "model_id": snapshot.get("model_id"),
            "thinking_level": snapshot.get("thinking_level"),
            "skill_name": snapshot.get("skill_name"),
        },
        "context_debug": snapshot.get("context_debug"),
    }


@router.get("/{run_id}/context-debug")
async def get_context_debug(run_id: str):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    snapshot = row.model_snapshot or {}
    return {
        "run_id": str(row.id),
        "conversation_id": str(row.conversation_id),
        "status": row.status,
        "mode": row.mode,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "context_debug": snapshot.get("context_debug"),
    }


@router.get("/{run_id}/checkpoints")
async def run_checkpoints(run_id: str):
    return await get_run_checkpoint(run_id)


class RestoreIn(BaseModel):
    mode: str = "run"  # run | to_before
    paths: list[str] | None = None


@router.post("/{run_id}/checkpoints/restore")
async def restore_checkpoint(run_id: str, body: RestoreIn):
    return await restore_run_files(run_id, mode=body.mode or "run", paths=body.paths)


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Query(default=None),
):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})

    async def gen():
        header_id = request.headers.get("last-event-id")
        cursor = last_event_id or header_id
        async for event in broker.tail(run_id, cursor):
            if await request.is_disconnected():
                break
            yield {"id": event["event_id"], "data": json.dumps(event, ensure_ascii=False)}
            if event["type"] in {"run.completed", "run.failed", "run.cancelled"}:
                break

    return EventSourceResponse(gen(), ping=15)


@router.post("/{run_id}/cancel")
async def stop_run(run_id: str):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    await cancel_run(run_id)
    return {"ok": True}


class ApprovalIn(BaseModel):
    allowed: bool = True


@router.post("/{run_id}/approvals/{approval_id}")
async def decide_approval(run_id: str, approval_id: str, body: ApprovalIn):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    try:
        await resolve_approval(run_id, approval_id, body.allowed)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "approval.not_found"}) from None
    return {"ok": True, "allowed": body.allowed}
