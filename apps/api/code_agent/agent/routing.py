from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from code_agent.agent.state import AgentState


def route_after_prepare(state: AgentState) -> Literal["compress", "agent"]:
    if state.get("needs_compress"):
        return "compress"
    return "agent"


def route_after_agent(state: AgentState) -> Literal["tools", "end"]:
    messages = state.get("messages") or []
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"
