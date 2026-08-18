from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel

from code_agent.db.models import Run
from code_agent.streaming.broker import broker
from code_agent.streaming.run_manager import cancel_run
from code_agent.tools.approval import resolve_approval

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: str):
    row = await Run.get_or_none(id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
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
    }


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
