from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    workspace_id: str
    conversation_id: str
    run_id: str
    mode: str
    thinking_level: str
    system_prompt: str
    memory_facts: list[dict[str, Any]]
    conversation_summary: str
    needs_compress: bool
    token_estimate: int
    window_message_ids: list[str]
    outside_sort_keys: list[int]
