from __future__ import annotations

from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES


def replace_state_messages(messages: list) -> list:
    """Replace checkpoint messages instead of appending (per-run fresh context)."""
    return [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]
