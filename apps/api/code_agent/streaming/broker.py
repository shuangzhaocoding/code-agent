from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

from code_agent.db.models import Conversation, Message, Run, RunEvent


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventBroker:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        async with self._lock:
            run = await Run.get(id=run_id)
            seq = int(run.last_seq or 0) + 1
            event_id = f"{seq:08d}-{uuid4().hex[:8]}"
            envelope = {
                "v": 1,
                "event_id": event_id,
                "run_id": str(run_id),
                "ts": _utcnow(),
                "type": event_type,
                "seq": seq,
                "payload": payload,
            }
            await RunEvent.create(
                run_id=run_id,
                event_id=event_id,
                seq=seq,
                type=event_type,
                payload=payload,
            )
            await self._materialize(run, envelope)
            run.last_seq = seq
            run.last_event_id = event_id
            await run.save(update_fields=["last_seq", "last_event_id"])
        for queue in list(self._subs.get(str(run_id), [])):
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                pass
        return envelope

    async def _materialize(self, run: Run, envelope: dict[str, Any]) -> None:
        et = envelope["type"]
        payload = envelope["payload"]
        if et == "block.started":
            from datetime import datetime, timezone
            msg = await self._assistant_message(run)
            blocks = list(msg.blocks or [])
            blocks.append(
                {
                    "id": payload["block_id"],
                    "type": payload.get("block_type") or "assistant.markdown",
                    "text": "",
                    "meta": payload.get("meta") or {},
                    "status": "streaming",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            msg.blocks = blocks
            await msg.save(update_fields=["blocks"])
        elif et == "block.delta":
            msg = await Message.filter(run_id=str(run.id), role="assistant").order_by("-sort_key").first()
            if not msg:
                return
            blocks = list(msg.blocks or [])
            for block in blocks:
                if block.get("id") == payload.get("block_id"):
                    block["text"] = (block.get("text") or "") + (payload.get("text") or "")
                    if payload.get("meta"):
                        block["meta"] = {**(block.get("meta") or {}), **payload["meta"]}
                    break
            msg.blocks = blocks
            await msg.save(update_fields=["blocks"])
        elif et == "block.completed":
            from datetime import datetime, timezone
            msg = await Message.filter(run_id=str(run.id), role="assistant").order_by("-sort_key").first()
            if not msg:
                return
            blocks = list(msg.blocks or [])
            for block in blocks:
                if block.get("id") == payload.get("block_id"):
                    if payload.get("meta"):
                        block["meta"] = {**(block.get("meta") or {}), **payload["meta"]}
                    block["status"] = payload.get("status") or "ok"
                    block["ended_at"] = datetime.now(timezone.utc).isoformat()
                    break
            msg.blocks = blocks
            await msg.save(update_fields=["blocks"])
        elif et in {"run.completed", "run.failed", "run.cancelled"}:
            conv = await Conversation.get(id=run.conversation_id)
            if conv.active_run_id == str(run.id):
                conv.active_run_id = None
                await conv.save(update_fields=["active_run_id", "updated_at"])

    async def _assistant_message(self, run: Run) -> Message:
        msg = await Message.filter(run_id=str(run.id), role="assistant").first()
        if msg:
            return msg
        last = await Message.filter(conversation_id=run.conversation_id).order_by("-sort_key").first()
        sort_key = (last.sort_key + 1) if last else 1
        return await Message.create(
            conversation_id=run.conversation_id,
            role="assistant",
            blocks=[],
            run_id=str(run.id),
            sort_key=sort_key,
        )

    async def replay(self, run_id: str, last_event_id: str | None) -> list[dict[str, Any]]:
        last_seq = 0
        if last_event_id:
            prev = await RunEvent.filter(event_id=last_event_id).first()
            if prev:
                last_seq = prev.seq
        rows = await RunEvent.filter(run_id=run_id, seq__gt=last_seq).order_by("seq")
        return [
            {
                "v": 1,
                "event_id": r.event_id,
                "run_id": str(run_id),
                "ts": r.created_at.isoformat() if r.created_at else _utcnow(),
                "type": r.type,
                "seq": r.seq,
                "payload": r.payload,
            }
            for r in rows
        ]

    async def tail(self, run_id: str, last_event_id: str | None) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs[str(run_id)].append(queue)
        seen: set[str] = set()
        try:
            for event in await self.replay(run_id, last_event_id):
                seen.add(event["event_id"])
                yield event
            while True:
                try:
                    event = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if event is None:
                    return
                if event["event_id"] not in seen:
                    seen.add(event["event_id"])
                    yield event
            while True:
                event = await queue.get()
                if event is None:
                    return
                if event["event_id"] in seen:
                    continue
                seen.add(event["event_id"])
                yield event
        finally:
            subs = self._subs.get(str(run_id), [])
            if queue in subs:
                subs.remove(queue)

    def close_run(self, run_id: str) -> None:
        for queue in list(self._subs.get(str(run_id), [])):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass


broker = EventBroker()
