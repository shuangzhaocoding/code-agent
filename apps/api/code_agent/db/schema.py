from __future__ import annotations

from tortoise import Tortoise


async def upgrade_llm_schema() -> None:
    """Add new LLM columns on existing SQLite databases."""
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict("PRAGMA table_info(llm_models)")
    cols = {row["name"] for row in rows}
    if "capabilities_json" not in cols:
        await conn.execute_script(
            "ALTER TABLE llm_models ADD COLUMN capabilities_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "params_json" not in cols:
        await conn.execute_script(
            "ALTER TABLE llm_models ADD COLUMN params_json TEXT NOT NULL DEFAULT '{}'"
        )
