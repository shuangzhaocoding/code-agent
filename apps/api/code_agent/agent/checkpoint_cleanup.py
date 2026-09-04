from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import aiosqlite

from code_agent.agent.checkpointer import checkpoint_db_path, get_checkpointer, graph_thread_id
from code_agent.config import settings

logger = logging.getLogger(__name__)


def _cleanup_enabled() -> bool:
    return bool(settings.get("agent.checkpoint_cleanup.enabled", True))


def _cleanup_on_run_end() -> str:
    mode = str(settings.get("agent.checkpoint_cleanup.on_run_end") or "delete").strip().lower()
    return mode if mode in {"delete", "off"} else "delete"


def _orphan_cleanup_on_startup() -> bool:
    return bool(settings.get("agent.checkpoint_cleanup.orphan_on_startup", True))


def _vacuum_after_bulk() -> bool:
    return bool(settings.get("agent.checkpoint_cleanup.vacuum_after_bulk", True))


async def list_checkpoint_thread_ids() -> list[str]:
    path = checkpoint_db_path()
    try:
        async with aiosqlite.connect(path) as db:
            async with db.execute("SELECT DISTINCT thread_id FROM checkpoints") as cursor:
                rows = await cursor.fetchall()
    except Exception as exc:
        logger.debug("checkpoint list threads failed: %s", exc)
        return []
    return [str(row[0]) for row in rows if row and row[0]]


async def delete_thread_checkpoint(thread_id: str) -> bool:
    """Remove all checkpoint rows for a conversation thread."""
    if not thread_id:
        return False
    try:
        saver = get_checkpointer()
    except RuntimeError:
        logger.debug("checkpointer unavailable; skip delete thread %s", thread_id)
        return False
    try:
        await saver.adelete_thread(str(thread_id))
        return True
    except Exception as exc:
        logger.warning("failed to delete checkpoint thread %s: %s", thread_id, exc)
        return False


async def delete_conversation_checkpoint(workspace_id: str, conversation_id: str) -> bool:
    thread = graph_thread_id(str(workspace_id), str(conversation_id))
    return await delete_thread_checkpoint(thread)


async def cleanup_thread_after_run(thread_id: str | None) -> None:
    """Drop checkpoint data once a run finishes (UI history lives in Message DB)."""
    if not _cleanup_enabled() or _cleanup_on_run_end() != "delete" or not thread_id:
        return
    await delete_thread_checkpoint(str(thread_id))


def schedule_cleanup_after_run(thread_id: str | None) -> None:
    if not thread_id or not _cleanup_enabled() or _cleanup_on_run_end() != "delete":
        return

    async def _run() -> None:
        try:
            await cleanup_thread_after_run(thread_id)
        except Exception as exc:
            logger.debug("background checkpoint cleanup failed for %s: %s", thread_id, exc)

    asyncio.create_task(_run())


async def _valid_thread_ids() -> set[str]:
    from code_agent.db.models import Conversation

    rows = await Conversation.all().values_list("workspace_id", "id")
    return {graph_thread_id(str(ws_id), str(conv_id)) for ws_id, conv_id in rows}


async def cleanup_orphan_threads(*, vacuum: bool | None = None) -> dict[str, int]:
    """Delete checkpoint threads that no longer map to a conversation."""
    if not _cleanup_enabled():
        return {"orphans": 0, "deleted": 0, "vacuumed": 0}

    known = await _valid_thread_ids()
    present = await list_checkpoint_thread_ids()
    orphans = [thread_id for thread_id in present if thread_id not in known]
    deleted = 0
    for thread_id in orphans:
        if await delete_thread_checkpoint(thread_id):
            deleted += 1

    vacuumed = 0
    if deleted and (vacuum if vacuum is not None else _vacuum_after_bulk()):
        if await vacuum_checkpoint_db():
            vacuumed = 1

    if deleted:
        logger.info("checkpoint cleanup removed %s orphan thread(s)", deleted)
    return {"orphans": len(orphans), "deleted": deleted, "vacuumed": vacuumed}


async def vacuum_checkpoint_db() -> bool:
    path = checkpoint_db_path()
    try:
        async with aiosqlite.connect(path) as db:
            await db.execute("VACUUM")
            await db.commit()
        return True
    except Exception as exc:
        logger.warning("checkpoint VACUUM failed: %s", exc)
        return False


async def cleanup_threads(thread_ids: Iterable[str]) -> int:
    deleted = 0
    for thread_id in thread_ids:
        if await delete_thread_checkpoint(str(thread_id)):
            deleted += 1
    if deleted and _vacuum_after_bulk():
        await vacuum_checkpoint_db()
    return deleted


def schedule_startup_checkpoint_cleanup() -> None:
    if not _cleanup_enabled() or not _orphan_cleanup_on_startup():
        return

    async def _run() -> None:
        try:
            await cleanup_orphan_threads()
        except Exception as exc:
            logger.warning("startup checkpoint cleanup failed: %s", exc)

    asyncio.create_task(_run())
