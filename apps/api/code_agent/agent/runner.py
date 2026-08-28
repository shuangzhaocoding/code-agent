from __future__ import annotations

import asyncio

from code_agent.agent.checkpointer import graph_thread_id
from code_agent.agent.graph import build_agent_graph
from code_agent.agent.stream_adapter import stream_graph_events
from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Run, Setting, Workspace
from code_agent.llm.hub import resolve_chat_model
from code_agent.llm.thinking import normalize_thinking_level
from code_agent.llm.vision import is_image_file_meta, message_files, message_text, turn_needs_vision
from code_agent.plugins.base import registry
from code_agent.protocol.events import new_id
from code_agent.skills.registry import load_skill_body
from code_agent.streaming.broker import broker
from code_agent.tools.context import set_tool_context
from code_agent.tools.host import register_builtin_tools


async def run_agent_graph(
    run_id: str,
    *,
    cancel_event: asyncio.Event,
) -> None:
    register_builtin_tools()
    run = await Run.get(id=run_id)
    conv = await Conversation.get(id=run.conversation_id)
    workspace = await Workspace.get(id=conv.workspace_id)
    thinking_level = normalize_thinking_level((run.model_snapshot or {}).get("thinking_level"))
    if not (run.model_snapshot or {}).get("thinking_level") and (run.model_snapshot or {}).get("thinking"):
        thinking_level = "medium"

    history = await Message.filter(conversation_id=conv.id).order_by("sort_key")
    latest_user = next((row for row in reversed(history) if row.role == "user"), None)
    current_files = message_files(latest_user.blocks) if latest_user else []
    current_text = message_text(latest_user.blocks) if latest_user else ""
    history_has_images = any(
        is_image_file_meta(item)
        for row in history
        if row.role == "user"
        for item in message_files(row.blocks)
    )
    need_vision = turn_needs_vision(
        current_text=current_text,
        current_files=current_files,
        history_has_images=history_has_images,
    )

    from code_agent.llm.hub import model_has_vision

    model, model_row, switch_info = await resolve_chat_model(
        conv.model_id,
        thinking_level,
        need_vision=need_vision,
        prefer_tools=run.mode == "agent",
    )
    if model is None:
        raise RuntimeError("model.missing")
    if model_row and not model_row.supports_tools and run.mode == "agent":
        raise RuntimeError("model.unsupported_tools")
    vision = model_has_vision(model_row)
    if need_vision and not vision:
        raise RuntimeError("model.unsupported_vision")

    if switch_info and switch_info.get("reason") == "vision":
        snap = dict(run.model_snapshot or {})
        snap["auto_vision_switch"] = switch_info
        snap["effective_model_id"] = str(model_row.id)
        snap["effective_model"] = model_row.model_id
        run.model_snapshot = snap
        await run.save(update_fields=["model_snapshot"])
        notice_id = new_id()
        notice = (
            f"已自动切换到视觉模型 **{switch_info['to_name']}**"
            f"（`{switch_info['to_model_id']}`），"
            f"原模型 `{switch_info['from_name']}` 不支持图片理解。"
        )
        await broker.publish(
            run_id,
            "block.started",
            {
                "block_id": notice_id,
                "block_type": "assistant.markdown",
                "meta": {"kind": "model_switch", "auto_vision_switch": switch_info},
            },
        )
        await broker.publish(run_id, "block.delta", {"block_id": notice_id, "text": notice})
        await broker.publish(run_id, "block.completed", {"block_id": notice_id, "status": "ok"})

    set_tool_context(run_id, {"id": str(workspace.id), "root_path": workspace.root_path})
    tools = registry.enabled_tools(run.mode)

    skill_name = (run.model_snapshot or {}).get("skill_name")
    if not skill_name and latest_user:
        skill_meta = (latest_user.blocks[0].get("meta") or {}).get("skill") if latest_user.blocks else None
        if isinstance(skill_meta, dict):
            skill_name = skill_meta.get("name")
    skill_body = None
    if skill_name:
        skill_body = load_skill_body(workspace.root_path, str(skill_name))
        if skill_body:
            block_id = new_id()
            await broker.publish(
                run_id,
                "block.started",
                {"block_id": block_id, "block_type": "skill.activated", "meta": {"name": skill_name}},
            )
            await broker.publish(run_id, "block.delta", {"block_id": block_id, "text": skill_body[:500]})
            await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "ok"})

    thread = graph_thread_id(str(workspace.id), str(conv.id))
    run.graph_thread_id = thread
    await run.save(update_fields=["graph_thread_id"])

    recursion_limit = int(settings.get("agent.max_steps") or 80)
    stored_limit = await Setting.get_or_none(key="agent.max_steps")
    if stored_limit is not None and stored_limit.value_json is not None:
        try:
            recursion_limit = int(stored_limit.value_json)
        except (TypeError, ValueError):
            pass

    graph = build_agent_graph(tools)
    input_state = {
        "workspace_id": str(workspace.id),
        "conversation_id": str(conv.id),
        "run_id": run_id,
        "mode": run.mode,
        "thinking_level": thinking_level,
        "messages": [],
    }
    config = {
        "configurable": {
            "thread_id": thread,
            "model": model,
            "tools": tools,
            "vision": vision,
            "need_vision": need_vision,
            "skill_name": str(skill_name) if skill_name and skill_body else None,
            "skill_body": skill_body,
            "user_query": current_text,
        },
        "recursion_limit": max(1, recursion_limit),
    }

    await stream_graph_events(
        run_id,
        graph,
        input_state,
        config,
        thinking_level=thinking_level,
        cancel_event=cancel_event,
    )

    if cancel_event.is_set():
        return

    # Memory extraction is internal — run in background so run.completed is not delayed.
    if settings.get("agent.memory.enabled", True):

        async def _extract_bg() -> None:
            from code_agent.agent.memory.extract import extract_workspace_memories

            try:
                await extract_workspace_memories(
                    workspace_id=str(workspace.id),
                    conversation_id=str(conv.id),
                    run_id=run_id,
                    model=model,
                )
            except Exception:
                pass

        asyncio.create_task(_extract_bg())
