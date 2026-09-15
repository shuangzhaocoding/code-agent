from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from code_agent.agent.context_builder import build_run_context
from code_agent.agent.context_debug import persist_context_debug
from code_agent.agent.messages import replace_state_messages
from code_agent.agent.state import AgentState
from code_agent.db.models import Conversation, Workspace
from code_agent.protocol.events import new_id
from code_agent.streaming.broker import broker


def _context_injected_summary(debug: dict[str, Any]) -> str:
    rules = debug.get("rules") or {}
    injected = rules.get("injected") or []
    omitted = rules.get("omitted") or []
    memories = debug.get("memories") or []
    catalog = debug.get("skills_catalog") or []
    active = debug.get("active_skill")
    lines = [
        f"mode={debug.get('mode')} thinking={debug.get('thinking_level')}",
        f"rules injected={len(injected)} omitted={len(omitted)}"
        + (" (truncated)" if rules.get("truncated") else ""),
        f"skills catalog={len(catalog)}",
        f"memories={len(memories)}",
        f"window msgs={((debug.get('window') or {}).get('message_count') or 0)}"
        f" ~{((debug.get('window') or {}).get('token_estimate') or 0)} tokens",
    ]
    if active:
        lines.append(f"active skill=@{active.get('name')} via {active.get('source')}")
    if injected:
        lines.append("rules: " + ", ".join(r.get("path") or "?" for r in injected[:8]))
    return "\n".join(lines)


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
        skill_source=cfg.get("skill_source"),
        user_query=str(cfg.get("user_query") or ""),
    )
    debug = ctx.get("context_debug") or {}
    run_id = state.get("run_id")
    if run_id and debug:
        await persist_context_debug(str(run_id), debug)
        block_id = new_id()
        await broker.publish(
            str(run_id),
            "block.started",
            {
                "block_id": block_id,
                "block_type": "context.injected",
                "meta": {
                    "rules_count": len((debug.get("rules") or {}).get("injected") or []),
                    "memories_count": len(debug.get("memories") or []),
                    "skills_catalog_count": len(debug.get("skills_catalog") or []),
                    "active_skill": (debug.get("active_skill") or {}).get("name"),
                    "token_estimate": (debug.get("window") or {}).get("token_estimate"),
                },
            },
        )
        await broker.publish(
            str(run_id),
            "block.delta",
            {"block_id": block_id, "text": _context_injected_summary(debug)},
        )
        await broker.publish(str(run_id), "block.completed", {"block_id": block_id, "status": "ok"})

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
