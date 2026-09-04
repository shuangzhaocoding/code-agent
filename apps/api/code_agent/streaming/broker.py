from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

from code_agent.db.models import Conversation, Message, Run, RunEvent
from code_agent.storage.events import events_use_redis, publish_run_event


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventBroker:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._delta_pending: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._delta_db_buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._flush_tasks: dict[str, asyncio.Task] = {}
        self._assistant_cache: dict[str, str] = {}
        self._run_seq: dict[str, int] = {}

    def _lock(self, run_id: str) -> asyncio.Lock:
        return self._locks[str(run_id)]

    async def publish(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        rid = str(run_id)
        if event_type == "block.delta":
            envelope = await self._publish_delta(rid, payload)
            return envelope

        async with self._lock(rid):
            await self._flush_run_buffers(rid)
            envelope = await self._persist_event_unlocked(rid, event_type, payload)
            if event_type in {"run.completed", "run.failed", "run.cancelled"}:
                await self._delete_delta_events(rid)
                self._assistant_cache.pop(rid, None)
                self._run_seq.pop(rid, None)
        self._broadcast(rid, envelope)
        await publish_run_event(rid, envelope)
        return envelope

    async def _alloc_seq(self, run_id: str, run: Run) -> int:
        if run_id not in self._run_seq:
            self._run_seq[run_id] = int(run.last_seq or 0)
        self._run_seq[run_id] += 1
        return self._run_seq[run_id]

    async def _publish_delta(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        block_id = str(payload.get("block_id") or "")
        text = str(payload.get("text") or "")
        meta = payload.get("meta")

        async with self._lock(run_id):
            run = await Run.get(id=run_id)
            seq = await self._alloc_seq(run_id, run)
            event_id = f"{seq:08d}-{uuid4().hex[:8]}"
            envelope = {
                "v": 1,
                "event_id": event_id,
                "run_id": run_id,
                "ts": _utcnow(),
                "type": "block.delta",
                "seq": seq,
                "payload": payload,
            }
            self._delta_db_buffer[run_id].append(envelope)

            pending = self._delta_pending[run_id].setdefault(block_id, {"text": "", "meta": {}})
            pending["text"] += text
            if meta:
                pending["meta"].update(meta)
            self._schedule_run_flush(run_id)

        self._broadcast(run_id, envelope)
        await publish_run_event(run_id, envelope)
        return envelope

    def _schedule_run_flush(self, run_id: str) -> None:
        if run_id in self._flush_tasks and not self._flush_tasks[run_id].done():
            return

        async def _delayed() -> None:
            try:
                await asyncio.sleep(0.2)
                async with self._lock(run_id):
                    await self._flush_run_buffers_unlocked(run_id)
            except asyncio.CancelledError:
                return

        self._flush_tasks[run_id] = asyncio.create_task(_delayed())

    async def _flush_run_buffers(self, run_id: str) -> None:
        task = self._flush_tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._flush_run_buffers_unlocked(run_id)

    async def _flush_run_buffers_unlocked(self, run_id: str) -> None:
        await self._flush_message_deltas(run_id)

        batch = self._delta_db_buffer.pop(run_id, [])
        if not batch:
            return

        run = await Run.get(id=run_id)
        rows = [
            RunEvent(
                run_id=run_id,
                event_id=env["event_id"],
                seq=int(env["seq"]),
                type=env["type"],
                payload=env["payload"],
            )
            for env in batch
        ]
        await RunEvent.bulk_create(rows)
        last = batch[-1]
        run.last_seq = int(last["seq"])
        run.last_event_id = str(last["event_id"])
        await run.save(update_fields=["last_seq", "last_event_id"])

    async def _flush_message_deltas(self, run_id: str) -> None:
        pending = self._delta_pending.get(run_id)
        if not pending:
            return

        run = await Run.get(id=run_id)
        # Avoid stale ORM cache missing freshly materialized blocks/text.
        self._assistant_cache.pop(str(run_id), None)
        msg = await Message.filter(run_id=str(run.id), role="assistant").first()
        if msg is None:
            return

        blocks = list(msg.blocks or [])
        by_id = {str(b.get("id")): b for b in blocks if b.get("id")}

        changed = False
        merged_ids: list[str] = []
        for block_id, chunk in pending.items():
            block = by_id.get(str(block_id))
            if block is None:
                continue
            text = str(chunk.get("text") or "")
            if text:
                block["text"] = (block.get("text") or "") + text
                changed = True
            meta = chunk.get("meta")
            if meta:
                block["meta"] = {**(block.get("meta") or {}), **meta}
                changed = True
            merged_ids.append(str(block_id))

        if changed:
            msg.blocks = blocks
            await msg.save(update_fields=["blocks"])

        for block_id in merged_ids:
            pending.pop(block_id, None)
        if not pending:
            self._delta_pending.pop(run_id, None)

    async def _delete_delta_events(self, run_id: str) -> None:
        await RunEvent.filter(run_id=run_id, type="block.delta").delete()

    async def _persist_event_unlocked(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        run = await Run.get(id=run_id)
        seq = await self._alloc_seq(run_id, run)
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
        return envelope

    def _broadcast(self, run_id: str, envelope: dict[str, Any]) -> None:
        for queue in list(self._subs.get(str(run_id), [])):
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                pass

    async def _materialize(self, run: Run, envelope: dict[str, Any]) -> None:
        et = envelope["type"]
        payload = envelope["payload"]
        if et == "block.started":
            msg = await self._assistant_message(run, cache=True)
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
            pass
        elif et == "block.completed":
            await self._flush_message_deltas(str(run.id))
            msg = await self._assistant_message(run, cache=False)
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

    async def _assistant_message(self, run: Run, *, cache: bool = False) -> Message:
        rid = str(run.id)
        if cache and rid in self._assistant_cache:
            msg = await Message.get_or_none(id=self._assistant_cache[rid])
            if msg:
                return msg
        msg = await Message.filter(run_id=rid, role="assistant").first()
        if msg:
            if cache:
                self._assistant_cache[rid] = str(msg.id)
            return msg
        last = await Message.filter(conversation_id=run.conversation_id).order_by("-sort_key").first()
        sort_key = (last.sort_key + 1) if last else 1
        msg = await Message.create(
            conversation_id=run.conversation_id,
            role="assistant",
            blocks=[],
            run_id=rid,
            sort_key=sort_key,
        )
        if cache:
            self._assistant_cache[rid] = str(msg.id)
        return msg

    async def replay(self, run_id: str, last_event_id: str | None) -> list[dict[str, Any]]:
        async with self._lock(str(run_id)):
            await self._flush_run_buffers(str(run_id))
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

    async def _poll_new_events(self, run_id: str, seen: set[str]) -> list[dict[str, Any]]:
        async with self._lock(str(run_id)):
            await self._flush_run_buffers(str(run_id))
        last_seq = 0
        if seen:
            row = await RunEvent.filter(run_id=run_id, event_id__in=list(seen)).order_by("-seq").first()
            if row:
                last_seq = row.seq
        rows = await RunEvent.filter(run_id=run_id, seq__gt=last_seq).order_by("seq")
        out = []
        for r in rows:
            if r.event_id in seen:
                continue
            out.append(
                {
                    "v": 1,
                    "event_id": r.event_id,
                    "run_id": str(run_id),
                    "ts": r.created_at.isoformat() if r.created_at else _utcnow(),
                    "type": r.type,
                    "seq": r.seq,
                    "payload": r.payload,
                }
            )
        return out

    async def _run_is_terminal(self, run_id: str) -> bool:
        run = await Run.get_or_none(id=run_id)
        return run is not None and run.status in {"completed", "failed", "cancelled"}

    async def tail(self, run_id: str, last_event_id: str | None) -> AsyncIterator[dict[str, Any]]:
        from code_agent.runtime.profile import agent_execution_external

        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs[str(run_id)].append(queue)
        seen: set[str] = set()
        remote = agent_execution_external() or events_use_redis()
        redis_task: asyncio.Task | None = None

        if remote and events_use_redis():
            from code_agent.storage.events import subscribe_run_events

            async def _redis_pump() -> None:
                try:
                    async for event in subscribe_run_events(run_id):
                        await queue.put(event)
                except asyncio.CancelledError:
                    return

            redis_task = asyncio.create_task(_redis_pump())

        try:
            for event in await self.replay(run_id, last_event_id):
                seen.add(event["event_id"])
                yield event
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.35)
                except asyncio.TimeoutError:
                    if remote:
                        for item in await self._poll_new_events(run_id, seen):
                            seen.add(item["event_id"])
                            yield item
                        if await self._run_is_terminal(run_id):
                            break
                    continue
                if event is None:
                    return
                if event["event_id"] not in seen:
                    seen.add(event["event_id"])
                    yield event
                if event.get("type") in {"run.completed", "run.failed", "run.cancelled"}:
                    return
        finally:
            if redis_task is not None:
                redis_task.cancel()
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
