from __future__ import annotations

import asyncio
from typing import Any

from code_agent.protocol.events import new_id
from code_agent.tools.context import get_run_id

_pending: dict[str, dict[str, Any]] = {}


async def request_approval(
    tool: str,
    summary: str,
    details: dict[str, Any] | None = None,
    kind: str = "danger",
) -> bool:
    """Pause a tool until the user approves or denies it in the UI.

    Returns True when not inside an agent run (REST / UI already confirmed).
    """
    try:
        run_id = get_run_id()
    except RuntimeError:
        return True

    from code_agent.streaming.broker import broker

    approval_id = new_id()
    block_id = new_id()
    event = asyncio.Event()
    _pending[approval_id] = {
        "event": event,
        "allowed": False,
        "run_id": run_id,
        "block_id": block_id,
        "tool": tool,
    }
    await broker.publish(
        run_id,
        "block.started",
        {
            "block_id": block_id,
            "block_type": "approval",
            "meta": {
                "approval_id": approval_id,
                "kind": kind,
                "tool": tool,
                "summary": summary,
                "details": details or {},
            },
        },
    )
    try:
        await asyncio.wait_for(event.wait(), timeout=600)
    except asyncio.TimeoutError:
        await _complete(approval_id, False)
        return False
    item = _pending.get(approval_id)
    allowed = bool(item and item.get("allowed"))
    await _complete(approval_id, allowed)
    return allowed


async def resolve_approval(run_id: str, approval_id: str, allowed: bool) -> None:
    item = _pending.get(approval_id)
    if not item or item["run_id"] != run_id:
        raise KeyError(approval_id)
    item["allowed"] = allowed
    item["event"].set()


async def deny_run_approvals(run_id: str) -> None:
    for item in list(_pending.values()):
        if item.get("run_id") == run_id and not item["event"].is_set():
            item["allowed"] = False
            item["event"].set()


async def _complete(approval_id: str, allowed: bool) -> None:
    item = _pending.pop(approval_id, None)
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
