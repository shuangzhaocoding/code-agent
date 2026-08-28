from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from code_agent.agent.memory.extract import extract_workspace_memories
from code_agent.agent.state import AgentState


async def extract_memory_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    model = cfg.get("model")
    if model is None:
        return {}
    await extract_workspace_memories(
        workspace_id=state["workspace_id"],
        conversation_id=state["conversation_id"],
        run_id=state["run_id"],
        model=model,
    )
    return {}
