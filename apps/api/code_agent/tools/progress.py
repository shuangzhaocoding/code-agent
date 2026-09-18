"""Track open tool.call blocks so tools can emit live progress mid-execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class _OpenTool:
    call_id: str
    block_id: str
    name: str


@dataclass
class _RunTools:
    # Newest last — current_block returns the latest matching open tool.
    stack: list[_OpenTool] = field(default_factory=list)


_lock = Lock()
_runs: dict[str, _RunTools] = {}


def bind(run_id: str, call_id: str, block_id: str, name: str) -> None:
    if not run_id or not block_id:
        return
    with _lock:
        bucket = _runs.setdefault(str(run_id), _RunTools())
        # Replace if same call_id already open (HITL resume reuse).
        for item in bucket.stack:
            if item.call_id == str(call_id):
                item.block_id = str(block_id)
                item.name = str(name or "tool")
                return
        bucket.stack.append(
            _OpenTool(call_id=str(call_id), block_id=str(block_id), name=str(name or "tool"))
        )


def unbind(run_id: str, call_id: str | None = None, block_id: str | None = None) -> None:
    rid = str(run_id or "")
    if not rid:
        return
    with _lock:
        bucket = _runs.get(rid)
        if not bucket:
            return
        if call_id:
            cid = str(call_id)
            bucket.stack = [x for x in bucket.stack if x.call_id != cid]
        elif block_id:
            bid = str(block_id)
            bucket.stack = [x for x in bucket.stack if x.block_id != bid]
        if not bucket.stack:
            _runs.pop(rid, None)


def clear_run(run_id: str) -> None:
    with _lock:
        _runs.pop(str(run_id or ""), None)


def current_block(run_id: str, name: str | None = None) -> str | None:
    rid = str(run_id or "")
    if not rid:
        return None
    with _lock:
        bucket = _runs.get(rid)
        if not bucket or not bucket.stack:
            return None
        if name:
            want = str(name)
            for item in reversed(bucket.stack):
                if item.name == want:
                    return item.block_id
            return None
        return bucket.stack[-1].block_id


async def emit_delta(run_id: str, text: str, *, name: str | None = None) -> None:
    if not text:
        return
    block_id = current_block(run_id, name=name)
    if not block_id:
        return
    from code_agent.streaming.broker import broker

    await broker.publish(str(run_id), "block.delta", {"block_id": block_id, "text": text})


async def emit_meta(run_id: str, meta: dict[str, Any], *, name: str | None = None) -> None:
    if not meta:
        return
    block_id = current_block(run_id, name=name)
    if not block_id:
        return
    from code_agent.streaming.broker import broker

    await broker.publish(
        str(run_id),
        "block.updated",
        {"block_id": block_id, "meta": meta},
    )
