from __future__ import annotations

import logging
from pathlib import Path

from tortoise import Tortoise

logger = logging.getLogger(__name__)

# Shared pragmas for app DB and LangGraph checkpoint DB.
SQLITE_PRAGMAS: tuple[tuple[str, int | str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("busy_timeout", 5000),
    ("temp_store", "MEMORY"),
    ("cache_size", -64000),  # ~64 MiB page cache
    ("mmap_size", 268435456),  # 256 MiB mmap
)


async def configure_tortoise_sqlite() -> None:
    """Tune the primary business SQLite connection (readers + writers)."""
    conn = Tortoise.get_connection("default")
    for key, value in SQLITE_PRAGMAS:
        if isinstance(value, str):
            await conn.execute_query(f"PRAGMA {key}={value}")
        else:
            await conn.execute_query(f"PRAGMA {key}={value}")
    logger.debug("SQLite pragmas applied to business DB")


async def configure_sqlite_file(path: str | Path) -> None:
    """Apply performance pragmas to any SQLite file (e.g. checkpoint DB)."""
    import aiosqlite

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        for key, value in SQLITE_PRAGMAS:
            if isinstance(value, str):
                await db.execute(f"PRAGMA {key}={value}")
            else:
                await db.execute(f"PRAGMA {key}={value}")
        await db.commit()
    logger.debug("SQLite pragmas applied to %s", db_path)
