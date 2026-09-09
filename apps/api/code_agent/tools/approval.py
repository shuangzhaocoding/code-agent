"""Tool-layer approvals backed by LangGraph ``interrupt`` + ``Command(resume=...)``.

``request_approval`` raises a graph interrupt (via ``interrupt()``). The stream loop
surfaces SSE approval cards, waits for ``POST /approvals/{id}``, then resumes with
``Command(resume=...)``. The interrupt id is the UI ``approval_id``.

In split mode the API gateway and agent worker are separate processes: decisions
arrive on the API and are bridged to the worker via ``approval_ipc``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import interrupt

from code_agent.protocol.events import new_id
from code_agent.tools import approval_ipc
from code_agent.tools.context import get_run_id

_pending: dict[str, dict[str, Any]] = {}
_run_waiters: dict[str, asyncio.Future] = {}


def runs_awaiting_approval(run_ids: list[str] | set[str] | None = None) -> set[str]:
    """Return run ids that currently have an undecided in-memory approval."""
    wanted = {str(rid) for rid in run_ids} if run_ids is not None else None
    out: set[str] = set()
    for item in _pending.values():
        if item.get("decided"):
            continue
        rid = str(item.get("run_id") or "")
        if not rid:
            continue
        if wanted is not None and rid not in wanted:
            continue
        out.add(rid)
    return out


def _resume_payload(batch_ids: list[str]) -> bool | dict[str, bool]:
    if len(batch_ids) == 1:
        item = _pending.get(batch_ids[0]) or {}
        return bool(item.get("allowed"))
    return {aid: bool((_pending.get(aid) or {}).get("allowed")) for aid in batch_ids}


def _finish_waiter(run_id: str, payload: bool | dict[str, bool]) -> None:
    fut = _run_waiters.pop(run_id, None)
    if fut is not None and not fut.done():
        fut.set_result(payload)


async def request_approval(
    tool: str,
    summary: str,
    details: dict[str, Any] | None = None,
    kind: str = "danger",
) -> bool:
    """Pause the graph until the user approves or denies this tool call.

    Returns True when not inside an agent run (REST / UI already confirmed),
    or when ``policy.auto_run`` allows the operation without confirmation.
    """
    try:
        get_run_id()
    except RuntimeError:
        return True

    from code_agent.policy.engine import tool_needs_approval

    if not await tool_needs_approval(tool, kind=kind, details=details or {}):
        return True

    decision = interrupt(
        {
            "tool": tool,
            "summary": summary,
            "details": details or {},
            "kind": kind,
        }
    )
    return bool(decision)


async def wait_for_approval_resume(
    run_id: str,
    interrupts: tuple[Any, ...] | list[Any],
    *,
    timeout: float = 600,
) -> bool | dict[str, bool]:
    """Publish approval SSE cards for graph interrupts and wait for UI decisions."""
    from code_agent.streaming.broker import broker

    batch_ids: list[str] = []
    cards: list[tuple[str, str, dict[str, Any]]] = []
    for item in interrupts:
        approval_id = str(getattr(item, "id", None) or new_id())
        raw = getattr(item, "value", item)
        meta = raw if isinstance(raw, dict) else {"summary": str(raw)}
        block_id = new_id()
        batch_ids.append(approval_id)
        cards.append((approval_id, block_id, meta))
        _pending[approval_id] = {
            "event": None,
            "allowed": False,
            "decided": False,
            "run_id": run_id,
            "block_id": block_id,
            "tool": meta.get("tool"),
            "batch_ids": batch_ids,
        }

    for approval_id in batch_ids:
        if approval_id in _pending:
            _pending[approval_id]["batch_ids"] = batch_ids

    # Register IPC before SSE so a fast UI click cannot race clear_run.
    approval_ipc.clear_run(run_id)
    approval_ipc.register_pending(run_id, batch_ids)

    for approval_id, block_id, meta in cards:
        await broker.publish(
            run_id,
            "block.started",
            {
                "block_id": block_id,
                "block_type": "approval",
                "meta": {
                    "approval_id": approval_id,
                    "kind": meta.get("kind") or "danger",
                    "tool": meta.get("tool") or "",
                    "summary": meta.get("summary") or "需要确认",
                    "details": meta.get("details") or {},
                },
            },
        )

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    old = _run_waiters.pop(run_id, None)
    if old is not None and not old.done():
        old.set_result(_resume_payload(batch_ids))
    _run_waiters[run_id] = fut

    async def _poll_remote_and_cancel() -> None:
        from code_agent.db.models import Run

        while not fut.done():
            row = await Run.get_or_none(id=run_id)
            if row and row.status == "cancelled":
                await deny_run_approvals(run_id)
                return
            for aid in batch_ids:
                item = _pending.get(aid)
                if not item or item.get("decided"):
                    continue
                decision = approval_ipc.take_decision(run_id, aid)
                if decision is None:
                    continue
                try:
                    await resolve_approval(run_id, aid, decision)
                except KeyError:
                    continue
            await asyncio.sleep(0.25)

    poll_task = asyncio.create_task(_poll_remote_and_cancel())
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        for approval_id in batch_ids:
            item = _pending.get(approval_id)
            if item and not item.get("decided"):
                item["allowed"] = False
                item["decided"] = True
                await _complete(approval_id, False)
        payload = False if len(batch_ids) == 1 else {aid: False for aid in batch_ids}
        _finish_waiter(run_id, payload)
        return payload
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        approval_ipc.clear_run(run_id)


async def resolve_approval(run_id: str, approval_id: str, allowed: bool) -> None:
    item = _pending.get(approval_id)
    if item is not None and item["run_id"] != run_id:
        raise KeyError(approval_id)
    if item is None:
        # Split mode: API process forwards the decision to the worker.
        from code_agent.db.models import Run

        row = await Run.get_or_none(id=run_id)
        if not row or row.status not in {"queued", "running"}:
            raise KeyError(approval_id)
        approval_ipc.put_decision(run_id, approval_id, allowed)
        return
    if item.get("decided"):
        return
    item["allowed"] = allowed
    item["decided"] = True
    await _complete(approval_id, allowed)

    batch_ids = list(item.get("batch_ids") or [approval_id])
    if not all((_pending.get(aid) or {}).get("decided") for aid in batch_ids):
        return
    payload = _resume_payload(batch_ids)
    _finish_waiter(run_id, payload)
    for aid in batch_ids:
        _pending.pop(aid, None)


async def deny_run_approvals(run_id: str) -> None:
    affected = [
        aid
        for aid, item in _pending.items()
        if item.get("run_id") == run_id and not item.get("decided")
    ]
    if not affected:
        # API-side cancel in split mode: deny whatever the worker registered.
        remote_ids = approval_ipc.list_pending(run_id)
        if remote_ids:
            for aid in remote_ids:
                approval_ipc.put_decision(run_id, aid, False)
            return
        if run_id in _run_waiters:
            _finish_waiter(run_id, False)
        return
    shared = list((_pending.get(affected[0]) or {}).get("batch_ids") or affected)
    for aid in shared:
        item = _pending.get(aid)
        if not item:
            continue
        if not item.get("decided"):
            item["allowed"] = False
            item["decided"] = True
            await _complete(aid, False)
        _pending.pop(aid, None)
    payload: bool | dict[str, bool] = False if len(shared) == 1 else {aid: False for aid in shared}
    _finish_waiter(run_id, payload)


async def _complete(approval_id: str, allowed: bool) -> None:
    item = _pending.get(approval_id)
    if not item:
        return
    from code_agent.streaming.broker import broker

    await broker.publish(
        item["run_id"],
        "block.delta",
        {"block_id": item["block_id"], "meta": {"decision": "approved" if allowed else "denied"}},
    )
    await broker.publish(
        item["run_id"],
        "block.completed",
        {"block_id": item["block_id"], "status": "ok" if allowed else "error"},
    )
