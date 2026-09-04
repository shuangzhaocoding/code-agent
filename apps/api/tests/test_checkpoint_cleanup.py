from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from code_agent.agent.checkpointer import graph_thread_id
from code_agent.agent import checkpoint_cleanup as cleanup
from code_agent.config import settings


@pytest.fixture
def temp_checkpoint_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "checkpoints.sqlite3"
        monkeypatch.setattr(cleanup, "checkpoint_db_path", lambda: str(path))
        yield path


async def _seed_checkpoint(path: Path, thread_id: str) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
            """
        )
        await db.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) VALUES (?, '', ?, ?, ?)",
            (thread_id, "cp1", b"{}", b"{}"),
        )
        await db.execute(
            "INSERT INTO writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value) VALUES (?, '', ?, ?, ?, ?, ?)",
            (thread_id, "cp1", "task1", 0, "messages", b"[]"),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_list_checkpoint_thread_ids(temp_checkpoint_db):
    thread = graph_thread_id("ws1", "conv1")
    await _seed_checkpoint(temp_checkpoint_db, thread)
    ids = await cleanup.list_checkpoint_thread_ids()
    assert ids == [thread]


@pytest.mark.asyncio
async def test_delete_thread_checkpoint_uses_saver():
    saver = AsyncMock()
    saver.adelete_thread = AsyncMock()
    with patch.object(cleanup, "get_checkpointer", return_value=saver):
        ok = await cleanup.delete_thread_checkpoint("ws:conv")
    assert ok is True
    saver.adelete_thread.assert_awaited_once_with("ws:conv")


@pytest.mark.asyncio
async def test_cleanup_orphan_threads(temp_checkpoint_db):
    orphan = graph_thread_id("missing-ws", "missing-conv")
    await _seed_checkpoint(temp_checkpoint_db, orphan)

    saver = AsyncMock()
    saver.adelete_thread = AsyncMock()

    with (
        patch.object(cleanup, "get_checkpointer", return_value=saver),
        patch.object(cleanup, "_valid_thread_ids", AsyncMock(return_value=set())),
        patch.object(cleanup, "_vacuum_after_bulk", return_value=False),
    ):
        result = await cleanup.cleanup_orphan_threads(vacuum=False)

    assert result["orphans"] == 1
    assert result["deleted"] == 1
    saver.adelete_thread.assert_awaited_once_with(orphan)


@pytest.mark.asyncio
async def test_schedule_cleanup_after_run_respects_off(monkeypatch):
    settings._cfg.setdefault("agent", {}).setdefault("checkpoint_cleanup", {})["on_run_end"] = "off"
    called = False

    async def _fake_cleanup(_thread_id: str | None) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cleanup, "cleanup_thread_after_run", _fake_cleanup)
    cleanup.schedule_cleanup_after_run("ws:conv")
    await asyncio.sleep(0)
    assert called is False


def test_graph_thread_id_format():
    assert graph_thread_id("abc", "def") == "abc:def"
