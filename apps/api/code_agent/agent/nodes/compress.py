from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig

from code_agent.agent.memory.extract import compress_conversation_summary
from code_agent.agent.messages import replace_state_messages
from code_agent.agent.state import AgentState
from code_agent.db.models import Conversation, Message


async def compress_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    model = cfg.get("model")
    sort_keys = state.get("outside_sort_keys") or []
    if not sort_keys or model is None:
        return {"needs_compress": False}
    outside_rows = await Message.filter(
        conversation_id=state["conversation_id"], sort_key__in=sort_keys
    ).order_by("sort_key")
    if not outside_rows:
        return {"needs_compress": False}

    conv = await Conversation.get(id=state["conversation_id"])
    summary = await compress_conversation_summary(str(conv.id), outside_rows, model)
    max_sort = max((r.sort_key for r in outside_rows), default=0)
    conv.summary = summary
    conv.summary_covers_sort_key = max_sort
    conv.summary_updated_at = datetime.now(timezone.utc)
    await conv.save(update_fields=["summary", "summary_covers_sort_key", "summary_updated_at"])

    # Rebuild messages with updated summary via prepare — keep current window messages
    window_ids = set(state.get("window_message_ids") or [])
    rows = await Message.filter(conversation_id=str(conv.id)).order_by("sort_key")
    inside = [r for r in rows if str(r.id) in window_ids] or rows[-12:]

    from code_agent.agent.context_builder import history_to_lc_messages
    from code_agent.agent.prompt import build_system_prompt
    from code_agent.db.models import Workspace
    from langchain_core.messages import SystemMessage

    workspace = await Workspace.get(id=state["workspace_id"])
    system = build_system_prompt(
        workspace,
        state.get("mode") or "agent",
        state.get("thinking_level") or "off",
        memory_facts=state.get("memory_facts") or [],
        conversation_summary=summary,
        skill_name=cfg.get("skill_name"),
        skill_body=cfg.get("skill_body"),
    )
    lc = [SystemMessage(content=system)] + history_to_lc_messages(
        inside, vision=bool(cfg.get("vision") and cfg.get("need_vision"))
    )
    return {
        "messages": replace_state_messages(lc),
        "system_prompt": system,
        "conversation_summary": summary,
        "needs_compress": False,
    }
