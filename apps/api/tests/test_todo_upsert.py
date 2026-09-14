"""In-place todo checklist updates (single block per run)."""

from __future__ import annotations

import asyncio

from code_agent.tools.todos import normalize_todos, render_todo_text, todo_summary


def test_normalize_and_render_roundtrip():
    items = normalize_todos(
        [
            {"id": "1", "content": "A", "status": "completed"},
            {"id": "2", "content": "B", "status": "in_progress"},
            {"id": "3", "content": "C", "status": "pending"},
        ]
    )
    text = render_todo_text(items)
    summary = todo_summary(items)
    assert "[x] A" in text
    assert "[>] B" in text
    assert "[ ] C" in text
    assert summary["total"] == 3
    assert summary["completed"] == 1
    assert summary["in_progress"] == 1


def test_emit_todo_updates_same_block(monkeypatch):
    from code_agent.tools import host as host_mod

    published: list[tuple[str, dict]] = []

    class FakeBroker:
        async def publish(self, run_id, event_type, payload=None):
            published.append((event_type, payload or {}))
            return {}

    monkeypatch.setattr(host_mod, "get_run_id", lambda: "run-1")
    monkeypatch.setattr("code_agent.streaming.broker.broker", FakeBroker())
    monkeypatch.setattr("code_agent.protocol.events.new_id", lambda: "todo-block-1")

    async def fake_find(_run_id: str):
        return None

    monkeypatch.setattr(host_mod, "_find_run_todo_block_id", fake_find)

    asyncio.run(
        host_mod._emit_todo({"items": [{"id": "1", "content": "A", "status": "pending"}], "total": 1}, "[ ] A")
    )
    assert published[0][0] == "block.started"
    assert published[0][1]["block_id"] == "todo-block-1"
    assert published[-1][0] == "block.completed"
    published.clear()

    async def find_existing(_run_id: str):
        return "todo-block-1"

    monkeypatch.setattr(host_mod, "_find_run_todo_block_id", find_existing)
    asyncio.run(
        host_mod._emit_todo(
            {"items": [{"id": "1", "content": "A", "status": "completed"}], "total": 1, "completed": 1},
            "[x] A",
        )
    )
    assert len(published) == 1
    assert published[0][0] == "block.updated"
    assert published[0][1]["block_id"] == "todo-block-1"
    assert published[0][1]["text"] == "[x] A"
    assert published[0][1]["meta"]["items"][0]["status"] == "completed"
