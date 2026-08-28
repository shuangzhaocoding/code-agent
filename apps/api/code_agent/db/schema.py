from __future__ import annotations

from tortoise import Tortoise


async def _column_exists(table: str, column: str) -> bool:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(f"PRAGMA table_info({table})")
    return column in {row["name"] for row in rows}


async def _table_exists(table: str) -> bool:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]
    )
    return bool(rows)


async def upgrade_llm_schema() -> None:
    """Apply incremental SQLite migrations."""
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

    if await _table_exists("conversations"):
        if not await _column_exists("conversations", "summary"):
            await conn.execute_script("ALTER TABLE conversations ADD COLUMN summary TEXT")
        if not await _column_exists("conversations", "summary_covers_sort_key"):
            await conn.execute_script(
                "ALTER TABLE conversations ADD COLUMN summary_covers_sort_key INTEGER NOT NULL DEFAULT 0"
            )
        if not await _column_exists("conversations", "summary_updated_at"):
            await conn.execute_script("ALTER TABLE conversations ADD COLUMN summary_updated_at TIMESTAMP")

    if await _table_exists("runs") and not await _column_exists("runs", "graph_thread_id"):
        await conn.execute_script("ALTER TABLE runs ADD COLUMN graph_thread_id VARCHAR(128)")

    if not await _table_exists("workspace_memories"):
        await conn.execute_script(
            """
            CREATE TABLE IF NOT EXISTS workspace_memories (
                id CHAR(36) NOT NULL PRIMARY KEY,
                workspace_id CHAR(36) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                kind VARCHAR(40) NOT NULL,
                subject VARCHAR(200) NOT NULL,
                content JSON NOT NULL,
                tags JSON NOT NULL,
                source JSON NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                superseded_by CHAR(36),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_workspace_memories_ws_kind ON workspace_memories(workspace_id, kind);
            CREATE INDEX IF NOT EXISTS idx_workspace_memories_ws_subject ON workspace_memories(workspace_id, subject);
            """
        )

    await conn.execute_script(
        "CREATE INDEX IF NOT EXISTS idx_messages_conv_sort ON messages(conversation_id, sort_key)"
    )
    await conn.execute_script(
        "CREATE INDEX IF NOT EXISTS idx_conversations_ws_updated ON conversations(workspace_id, updated_at)"
    )
