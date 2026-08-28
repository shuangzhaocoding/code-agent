from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from code_agent.config import settings

_saver: AsyncSqliteSaver | None = None


def checkpoint_db_path() -> str:
    raw = settings.get("paths.checkpoint_db", "auto")
    if raw is None or str(raw).strip().lower() in {"auto", "true", "1", ""}:
        return str(settings.data_dir / "langgraph_checkpoints.sqlite3")
    path = settings.data_dir / str(raw) if not str(raw).startswith("/") else str(raw)
    return str(path)


def graph_thread_id(workspace_id: str, conversation_id: str) -> str:
    return f"{workspace_id}:{conversation_id}"


@asynccontextmanager
async def checkpointer_lifespan() -> AsyncIterator[AsyncSqliteSaver]:
    global _saver
    async with AsyncSqliteSaver.from_conn_string(checkpoint_db_path()) as saver:
        _saver = saver
        try:
            yield saver
        finally:
            _saver = None


def get_checkpointer() -> AsyncSqliteSaver:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialized")
    return _saver
