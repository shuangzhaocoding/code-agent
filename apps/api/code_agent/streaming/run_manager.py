from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Run, Setting, Workspace
from code_agent.llm.hub import resolve_chat_model
from code_agent.llm.thinking import normalize_thinking_level
from code_agent.protocol.events import new_id
from code_agent.streaming.broker import broker
from code_agent.tools.context import set_tool_context
from code_agent.tools.host import register_builtin_tools

# Re-export for backward compatibility
from code_agent.agent.prompt import build_system_prompt as _system_prompt

_tasks: set[asyncio.Task] = set()
_cancel: dict[str, asyncio.Event] = {}


async def start_run(
    conversation_id: str,
    user_text: str,
    mode: str,
    model_id: str | None,
    references: list | None,
    thinking_level: str = "off",
    files: list | None = None,
    skill_name: str | None = None,
) -> Run:
    level = normalize_thinking_level(thinking_level)
    conv = await Conversation.get(id=conversation_id)
    last = await Message.filter(conversation_id=conversation_id).order_by("-sort_key").first()
    sort_key = (last.sort_key + 1) if last else 1
    meta: dict = {}
    if files:
        meta["files"] = files
    if skill_name:
        meta["skill"] = {"name": skill_name}
    blocks = [{"id": new_id(), "type": "user.text", "text": user_text, "meta": meta, "status": "ok"}]
    if references:
        blocks.append(
            {
                "id": new_id(),
                "type": "user.references",
                "text": "",
                "meta": {"references": references},
                "status": "ok",
            }
        )
    user_msg = await Message.create(
        conversation_id=conversation_id,
        role="user",
        blocks=blocks,
        sort_key=sort_key,
    )
    if conv.title == "New chat":
        title = (user_text or "").strip()[:72]
        if not title and files:
            title = str(files[0].get("name") or "图片消息")[:72]
        conv.title = title or "New chat"
    run = await Run.create(
        conversation_id=conversation_id,
        status="queued",
        mode=mode,
        model_snapshot={
            "model_id": model_id,
            "thinking_level": level,
            "thinking": level not in {"off", "none", ""},
            **({"skill_name": skill_name} if skill_name else {}),
        },
    )
    user_msg.run_id = str(run.id)
    await user_msg.save(update_fields=["run_id"])
    conv.active_run_id = str(run.id)
    conv.mode = mode
    conv.model_id = model_id
    await conv.save()
    task = asyncio.create_task(_execute(str(run.id)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return run


async def cancel_run(run_id: str) -> None:
    from code_agent.tools.approval import deny_run_approvals

    await deny_run_approvals(run_id)
    event = _cancel.get(run_id)
    if event:
        event.set()
    run = await Run.get_or_none(id=run_id)
    if run and run.status in {"queued", "running"}:
        run.status = "cancelled"
        run.ended_at = datetime.now(timezone.utc)
        await run.save()
        await broker.publish(run_id, "run.cancelled", {})
        broker.close_run(run_id)


async def _execute(run_id: str) -> None:
    _cancel[run_id] = asyncio.Event()
    run = await Run.get(id=run_id)
    recursion_limit = int(settings.get("agent.max_steps") or 80)
    stored_limit = await Setting.get_or_none(key="agent.max_steps")
    if stored_limit is not None and stored_limit.value_json is not None:
        try:
            recursion_limit = int(stored_limit.value_json)
        except (TypeError, ValueError):
            pass
    try:
        run.status = "running"
        await run.save(update_fields=["status"])
        await broker.publish(run_id, "run.started", {"mode": run.mode})

        timeout = int(settings.get("agent.run_timeout_sec") or 900)
        use_legacy = bool(settings.get("agent.use_legacy_react"))

        if use_legacy:
            await asyncio.wait_for(
                _execute_legacy(run_id, recursion_limit),
                timeout=timeout,
            )
        else:
            from code_agent.agent.runner import run_agent_graph

            await asyncio.wait_for(
                run_agent_graph(run_id, cancel_event=_cancel[run_id]),
                timeout=timeout,
            )

        if _cancel[run_id].is_set():
            return
        run = await Run.get(id=run_id)
        if run.status == "running":
            run.status = "completed"
            run.ended_at = datetime.now(timezone.utc)
            await run.save()
            await broker.publish(run_id, "run.completed", {"usage": run.usage_json})
    except asyncio.TimeoutError:
        await _fail(run_id, "run.timeout", "Run timed out")
    except asyncio.CancelledError:
        await broker.publish(run_id, "run.cancelled", {})
    except Exception as exc:
        if type(exc).__name__ == "GraphRecursionError" or "GRAPH_RECURSION_LIMIT" in str(exc):
            await _fail(
                run_id,
                "run.recursion_limit",
                f"已达到最大步数 {recursion_limit}。可在设置中提高「Agent 最大步数」。",
            )
            return
        code = str(exc)
        if code in {"model.missing", "model.unsupported_tools", "model.unsupported_vision"}:
            messages = {
                "model.missing": "没有可用的 LLM。请先在 Models 面板添加 Provider。",
                "model.unsupported_tools": "当前模型不支持工具调用，请改用 Ask 或更换模型。",
                "model.unsupported_vision": "当前消息需要理解图片，但没有可用的视觉模型。请在 Models 面板添加并启用视觉模型。",
            }
            await _fail(run_id, code, messages.get(code, code))
            return
        await _fail(run_id, "run.error", str(exc))
    finally:
        broker.close_run(run_id)
        _cancel.pop(run_id, None)


async def _execute_legacy(run_id: str, recursion_limit: int) -> None:
    """Fallback: langgraph.prebuilt.create_react_agent (pre-migration path)."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.prebuilt import create_react_agent

    from code_agent.agent.stream_adapter import stream_graph_events
    from code_agent.llm.hub import model_has_vision
    from code_agent.llm.vision import (
        is_image_file_meta,
        message_files,
        message_text,
        turn_needs_vision,
    )
    from code_agent.plugins.base import registry
    from code_agent.skills.registry import load_skill_body

    run = await Run.get(id=run_id)
    conv = await Conversation.get(id=run.conversation_id)
    workspace = await Workspace.get(id=conv.workspace_id)
    register_builtin_tools()
    thinking_level = normalize_thinking_level((run.model_snapshot or {}).get("thinking_level"))

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
    model, model_row, _switch = await resolve_chat_model(
        conv.model_id, thinking_level, need_vision=need_vision, prefer_tools=run.mode == "agent"
    )
    if model is None:
        raise RuntimeError("model.missing")
    vision = model_has_vision(model_row)
    set_tool_context(run_id, {"id": str(workspace.id), "root_path": workspace.root_path})
    tools = registry.enabled_tools(run.mode)
    graph = create_react_agent(
        model,
        tools,
        prompt=_system_prompt(workspace, run.mode, thinking_level),
    )
    from code_agent.agent.context_builder import history_to_lc_messages

    lc_messages = history_to_lc_messages(list(history), vision=vision and need_vision)
    await stream_graph_events(
        run_id,
        graph,
        {"messages": lc_messages},
        {"recursion_limit": max(1, recursion_limit)},
        thinking_level=thinking_level,
        cancel_event=_cancel[run_id],
    )


async def _fail(run_id: str, code: str, message: str) -> None:
    run = await Run.get(id=run_id)
    run.status = "failed"
    run.error_code = code
    run.error_message = message
    run.ended_at = datetime.now(timezone.utc)
    await run.save()
    block_id = new_id()
    await broker.publish(run_id, "block.started", {"block_id": block_id, "block_type": "error", "meta": {"code": code}})
    await broker.publish(run_id, "block.delta", {"block_id": block_id, "text": message})
    await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "error"})
    await broker.publish(run_id, "run.failed", {"code": code, "message": message})
