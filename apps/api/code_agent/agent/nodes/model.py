from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from code_agent.agent.state import AgentState


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    model = cfg.get("model")
    tools = cfg.get("tools") or []
    if model is None:
        raise RuntimeError("model missing in graph config")
    bound = model.bind_tools(tools) if tools else model
    response = await bound.ainvoke(state["messages"])
    return {"messages": [response]}
