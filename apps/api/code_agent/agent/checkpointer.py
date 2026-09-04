from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from code_agent.config import settings
from code_agent.db.sqlite_tuning import configure_sqlite_file
from code_agent.storage.backends import checkpoint_postgres_url, storage_checkpoint_backend

_saver: Any = None


def checkpoint_db_path() -> str:
    raw = settings.get("paths.checkpoint_db", "auto")
    if raw is None or str(raw).strip().lower() in {"auto", "true", "1", ""}:
        return str(settings.data_dir / "langgraph_checkpoints.sqlite3")
    path = settings.data_dir / str(raw) if not str(raw).startswith("/") else str(raw)
    return str(path)


def graph_thread_id(workspace_id: str, conversation_id: str) -> str:
    return f"{workspace_id}:{conversation_id}"


def _use_postgres_checkpoint() -> bool:
    return storage_checkpoint_backend() == "postgres" and bool(checkpoint_postgres_url())


@asynccontextmanager
async def checkpointer_lifespan() -> AsyncIterator[Any]:
    global _saver
    if _use_postgres_checkpoint():
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "storage.checkpoint=postgres requires `pip install langgraph-checkpoint-postgres psycopg[binary]`"
            ) from exc
        async with AsyncPostgresSaver.from_conn_string(checkpoint_postgres_url()) as saver:
            await saver.setup()
            _saver = saver
            try:
                yield saver
            finally:
                _saver = None
        return

    await configure_sqlite_file(checkpoint_db_path())
    async with AsyncSqliteSaver.from_conn_string(checkpoint_db_path()) as saver:
        _saver = saver
        try:
            yield saver
        finally:
            _saver = None


def get_checkpointer() -> Any:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialized")
    return _saver
