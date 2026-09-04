from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from tortoise import Tortoise

from code_agent.agent.checkpointer import checkpointer_lifespan
from code_agent.db.schema import upgrade_llm_schema
from code_agent.db.sqlite_tuning import configure_tortoise_sqlite
from code_agent.llm.hub import register_builtin_providers
from code_agent.plugins.loader import apply_plugin_states, load_plugins
from code_agent.storage.backends import resolve_database_url, storage_database_backend
from code_agent.tools.host import register_builtin_tools


async def _after_db_connect() -> None:
    register_builtin_providers()
    register_builtin_tools()
    load_plugins()
    await apply_plugin_states()
    await upgrade_llm_schema()
    if storage_database_backend() == "sqlite":
        await configure_tortoise_sqlite()


async def init_database() -> None:
    await Tortoise.init(
        db_url=resolve_database_url(),
        modules={"models": ["code_agent.db.models"]},
    )
    await Tortoise.generate_schemas()
    await _after_db_connect()


async def close_database() -> None:
    await Tortoise.close_connections()


@asynccontextmanager
async def bootstrap(*, with_checkpointer: bool = False) -> AsyncIterator[None]:
    checkpointer = checkpointer_lifespan() if with_checkpointer else _noop()
    async with checkpointer:
        await init_database()
        try:
            yield
        finally:
            await close_database()


@asynccontextmanager
async def _noop() -> AsyncIterator[None]:
    yield
