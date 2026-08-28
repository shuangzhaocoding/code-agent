from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from code_agent.agent.context_builder import build_run_context
from code_agent.agent.messages import replace_state_messages
from code_agent.agent.state import AgentState
from code_agent.db.models import Conversation, Workspace


async def prepare_context_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    workspace = await Workspace.get(id=state["workspace_id"])
    conversation = await Conversation.get(id=state["conversation_id"])
    ctx = await build_run_context(
        workspace=workspace,
        conversation=conversation,
        mode=state.get("mode") or "agent",
        thinking_level=state.get("thinking_level") or "off",
        vision=bool(cfg.get("vision")),
        need_vision=bool(cfg.get("need_vision")),
        skill_name=cfg.get("skill_name"),
        skill_body=cfg.get("skill_body"),
        user_query=str(cfg.get("user_query") or ""),
    )
    return {
        "messages": replace_state_messages(ctx["messages"]),
        "system_prompt": ctx["system_prompt"],
        "memory_facts": ctx["memory_facts"],
        "conversation_summary": ctx["conversation_summary"],
        "needs_compress": ctx["needs_compress"],
        "token_estimate": ctx["token_estimate"],
        "window_message_ids": ctx["window_message_ids"],
        "outside_sort_keys": [r.sort_key for r in ctx["outside_rows"]],
    }
