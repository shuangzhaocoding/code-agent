"""HITL interrupt + Command(resume=...) approval bridge."""

import asyncio
from types import SimpleNamespace
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from code_agent.tools import approval as approval_mod


@pytest.fixture(autouse=True)
def _clear_approval_state():
    approval_mod._pending.clear()
    approval_mod._run_waiters.clear()
    yield
    approval_mod._pending.clear()
    approval_mod._run_waiters.clear()


def test_resolve_approval_resumes_single_interrupt(monkeypatch):
    published: list[tuple[str, dict]] = []

    async def _publish(run_id, event_type, payload):
        published.append((event_type, payload))

    monkeypatch.setattr("code_agent.streaming.broker.broker.publish", _publish)

    async def _run():
        interrupts = (
            SimpleNamespace(
                id="aid-1",
                value={
                    "tool": "write_file",
                    "summary": "写入 a.py",
                    "details": {"path": "a.py"},
                    "kind": "write",
                },
            ),
        )
        task = asyncio.create_task(approval_mod.wait_for_approval_resume("run-1", interrupts, timeout=5))
        await asyncio.sleep(0)
        assert "aid-1" in approval_mod._pending
        assert any(evt == "block.started" and payload["block_type"] == "approval" for evt, payload in published)
        await approval_mod.resolve_approval("run-1", "aid-1", True)
        assert await task is True
        assert "aid-1" not in approval_mod._pending
        decisions = [p for evt, p in published if evt == "block.delta"]
        assert decisions and decisions[0]["meta"]["decision"] == "approved"

    asyncio.run(_run())


def test_resolve_approval_waits_for_all_in_batch(monkeypatch):
    async def _publish(run_id, event_type, payload):
        return None

    monkeypatch.setattr("code_agent.streaming.broker.broker.publish", _publish)

    async def _run():
        interrupts = (
            SimpleNamespace(id="a", value={"tool": "write_file", "summary": "w1", "kind": "write"}),
            SimpleNamespace(id="b", value={"tool": "delete_file", "summary": "d1", "kind": "delete"}),
        )
        task = asyncio.create_task(approval_mod.wait_for_approval_resume("run-2", interrupts, timeout=5))
        await asyncio.sleep(0)
        await approval_mod.resolve_approval("run-2", "a", True)
        assert not task.done()
        await approval_mod.resolve_approval("run-2", "b", False)
        assert await task == {"a": True, "b": False}

    asyncio.run(_run())


def test_deny_run_approvals_wakes_waiter(monkeypatch):
    async def _publish(run_id, event_type, payload):
        return None

    monkeypatch.setattr("code_agent.streaming.broker.broker.publish", _publish)

    async def _run():
        interrupts = (
            SimpleNamespace(id="x", value={"tool": "run_command", "summary": "rm", "kind": "command"}),
        )
        task = asyncio.create_task(approval_mod.wait_for_approval_resume("run-3", interrupts, timeout=5))
        await asyncio.sleep(0)
        await approval_mod.deny_run_approvals("run-3")
        assert await task is False

    asyncio.run(_run())


def test_resolve_approval_cross_process_via_ipc(tmp_path, monkeypatch):
    """Worker polls IPC decision written by the API gateway process."""
    from code_agent.tools import approval_ipc

    monkeypatch.setattr(approval_ipc.settings, "data_dir", tmp_path)

    class _Run:
        status = "running"

    async def _get_or_none(id=None):
        return _Run()

    monkeypatch.setattr("code_agent.db.models.Run.get_or_none", _get_or_none)

    async def _publish(run_id, event_type, payload):
        return None

    monkeypatch.setattr("code_agent.streaming.broker.broker.publish", _publish)

    async def _run():
        interrupts = (
            SimpleNamespace(id="remote-2", value={"tool": "write_file", "summary": "w2", "kind": "write"}),
        )
        task = asyncio.create_task(
            approval_mod.wait_for_approval_resume("run-remote-2", interrupts, timeout=5)
        )
        await asyncio.sleep(0.05)
        # Gateway writes decision without local waiter memory
        approval_ipc.put_decision("run-remote-2", "remote-2", True)
        assert await task is True

        # Gateway resolve_approval with no local pending persists IPC
        await approval_mod.resolve_approval("run-gone", "aid-x", True)
        assert approval_ipc.take_decision("run-gone", "aid-x") is True

    asyncio.run(_run())


def test_stream_resume_with_command(monkeypatch):
    """End-to-end: ToolNode interrupt → wait → Command(resume=True)."""

    class S(TypedDict):
        messages: Annotated[list, add_messages]

    @tool
    async def risky(x: str) -> str:
        """Needs approval."""
        allowed = interrupt({"tool": "risky", "summary": f"do {x}", "kind": "danger", "details": {}})
        return "ok" if allowed else "ERROR: denied"

    async def _run():
        graph = StateGraph(S)
        graph.add_node("tools", ToolNode([risky]))
        graph.add_edge(START, "tools")
        graph.add_edge("tools", END)
        app = graph.compile(checkpointer=MemorySaver())
        cfg = {"configurable": {"thread_id": "hitl-e2e"}}
        msg = AIMessage(content="", tool_calls=[{"name": "risky", "args": {"x": "hi"}, "id": "c1"}])

        async for _ in app.astream_events({"messages": [msg]}, version="v2", config=cfg):
            pass
        snap = await app.aget_state(cfg)
        assert snap.interrupts
        aid = snap.interrupts[0].id

        async def _publish(run_id, event_type, payload):
            return None

        monkeypatch.setattr("code_agent.streaming.broker.broker.publish", _publish)

        waiter = asyncio.create_task(approval_mod.wait_for_approval_resume("run-e2e", snap.interrupts, timeout=5))
        await asyncio.sleep(0)
        await approval_mod.resolve_approval("run-e2e", aid, True)
        resume_value = await waiter
        assert resume_value is True

        async for _ in app.astream_events(Command(resume=resume_value), version="v2", config=cfg):
            pass
        snap2 = await app.aget_state(cfg)
        assert not snap2.interrupts
        assert snap2.next == ()
        last = snap2.values["messages"][-1]
        assert last.content == "ok"

    asyncio.run(_run())
