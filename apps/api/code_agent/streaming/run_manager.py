from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Run, Setting, Workspace
from code_agent.llm.hub import resolve_chat_model
from code_agent.llm.thinking import normalize_thinking_level, thinking_enabled, thinking_prompt
from code_agent.plugins.base import registry
from code_agent.protocol.events import new_id
from code_agent.skills.registry import list_skill_catalog
from code_agent.streaming.broker import broker
from code_agent.tools.context import set_tool_context
from code_agent.tools.host import register_builtin_tools

_tasks: set[asyncio.Task] = set()
_cancel: dict[str, asyncio.Event] = {}


def _plan_format_rules(mode: str) -> str:
    if mode != "plan":
        return ""
    return """
When mode is plan:
- Research first with read-only tools if needed.
- Do not edit files or run mutating commands.
- End with a numbered plan the UI can render as cards, using this format:

## 计划
1. **任务标题**：这一步要做什么，涉及哪些文件
2. **任务标题**：具体动作与验收标准
3. **任务标题**：...

Each step must start with a number and a bold title, then a colon and one or two sentences.
Ask the user to confirm before implementation.
"""


def _system_prompt(workspace: Workspace, mode: str, thinking_level: str = "off") -> str:
    skills = list_skill_catalog(workspace.root_path)
    skill_lines = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skills if not s.get("invalid_reason")
    ) or "(none)"
    extra = settings.get("agent.system_prompt_extra") or ""
    return f"""You are Code Agent, a coding assistant working on a real workspace.

Workspace root: {workspace.root_path}
Mode: {mode}
- ask: read-only. Do not write files or run mutating commands.
- plan: research with read-only tools, then propose a numbered plan. Do not implement until the user confirms.
- agent: you may edit files and run commands inside the workspace.

Rules:
- Prefer search_replace over write_file for existing files.
- Use list_skills / load_skill when a skill matches the task.
- Use git_status / git_diff / git_log for version control; git_commit and git_push require user confirmation.
- Prefer paths relative to the workspace root; absolute paths and ~ are allowed when needed (e.g. ~/.code-agent/skills).
- Be concise. Show your work via tools rather than dumping huge code in chat.
- After edits, mention which files changed.
{thinking_prompt(thinking_level)}
{_plan_format_rules(mode)}

Available skills:
{skill_lines}

{extra}
""".strip()


def _history_messages(rows: list[Message], *, vision: bool = False) -> list:
    from code_agent.llm.vision import build_user_content, message_files

    out = []
    for row in rows:
        text_parts = []
        for block in row.blocks or []:
            if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
                text_parts.append(block["text"])
        text = "\n".join(text_parts).strip()
        if row.role == "user":
            files = message_files(row.blocks)
            content = build_user_content(text, files, vision=vision)
            if content is None:
                continue
            out.append(HumanMessage(content=content))
        elif row.role == "assistant":
            if not text:
                continue
            out.append(AIMessage(content=text))
    return out


async def start_run(
    conversation_id: str,
    user_text: str,
    mode: str,
    model_id: str | None,
    references: list | None,
    thinking_level: str = "off",
    files: list | None = None,
) -> Run:
    level = normalize_thinking_level(thinking_level)
    conv = await Conversation.get(id=conversation_id)
    last = await Message.filter(conversation_id=conversation_id).order_by("-sort_key").first()
    sort_key = (last.sort_key + 1) if last else 1
    blocks = [{"id": new_id(), "type": "user.text", "text": user_text, "meta": {}, "status": "ok"}]
    if files:
        blocks[0]["meta"] = {"files": files}
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
    await Message.create(
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
        model_snapshot={"model_id": model_id, "thinking_level": level, "thinking": thinking_enabled(level)},
    )
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
    conv = await Conversation.get(id=run.conversation_id)
    workspace = await Workspace.get(id=conv.workspace_id)
    register_builtin_tools()
    recursion_limit = int(settings.get("agent.max_steps") or 80)
    try:
        run.status = "running"
        await run.save(update_fields=["status"])
        await broker.publish(run_id, "run.started", {"mode": run.mode})
        thinking_level = normalize_thinking_level((run.model_snapshot or {}).get("thinking_level"))
        if not (run.model_snapshot or {}).get("thinking_level") and (run.model_snapshot or {}).get("thinking"):
            thinking_level = "medium"

        from code_agent.llm.hub import model_has_vision
        from code_agent.llm.vision import (
            is_image_file_meta,
            message_files,
            message_text,
            turn_needs_vision,
        )

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
        # Prefer this turn's intent; only pull vision from context when text refers to prior images.
        need_vision = turn_needs_vision(
            current_text=current_text,
            current_files=current_files,
            history_has_images=history_has_images,
        )

        model, model_row, switch_info = await resolve_chat_model(
            conv.model_id,
            thinking_level,
            need_vision=need_vision,
            prefer_tools=run.mode == "agent",
        )
        if model is None:
            await _fail(run_id, "model.missing", "没有可用的 LLM。请先在 Models 面板添加 Provider。")
            return
        if model_row and not model_row.supports_tools and run.mode == "agent":
            await _fail(run_id, "model.unsupported_tools", "当前模型不支持工具调用，请改用 Ask 或更换模型。")
            return

        vision = model_has_vision(model_row)
        if need_vision and not vision:
            await _fail(
                run_id,
                "model.unsupported_vision",
                "当前消息需要理解图片，但没有可用的视觉模型。请在 Models 面板添加并启用视觉模型（如 deepseek-v4-flash-vision-exp）。",
            )
            return

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
        from langgraph.prebuilt import create_react_agent

        graph = create_react_agent(model, tools, prompt=_system_prompt(workspace, run.mode, thinking_level))
        # Only attach image bytes when this turn actually needs vision.
        lc_messages = _history_messages(list(history), vision=vision and need_vision)

        timeout = int(settings.get("agent.run_timeout_sec") or 900)
        stored_limit = await Setting.get_or_none(key="agent.max_steps")
        if stored_limit is not None and stored_limit.value_json is not None:
            try:
                recursion_limit = int(stored_limit.value_json)
            except (TypeError, ValueError):
                pass
        await asyncio.wait_for(
            _stream_graph(run_id, graph, lc_messages, thinking_level, recursion_limit),
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
        await _fail(run_id, "run.error", str(exc))
    finally:
        broker.close_run(run_id)
        _cancel.pop(run_id, None)


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


def _thinking_from_chunk(chunk) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, (list, tuple)):
        return "".join(_thinking_from_chunk(item) for item in chunk)
    msg = getattr(chunk, "message", None)
    if msg is not None and msg is not chunk:
        inner = _thinking_from_chunk(msg)
        if inner:
            return inner
    thinking = ""
    extra = getattr(chunk, "additional_kwargs", None) or {}
    if isinstance(extra, dict):
        thinking += extra.get("reasoning_content") or extra.get("reasoning") or ""
    if isinstance(chunk, dict):
        thinking += chunk.get("reasoning_content") or chunk.get("reasoning") or ""
        extra = chunk.get("additional_kwargs") or {}
        if isinstance(extra, dict):
            thinking += extra.get("reasoning_content") or extra.get("reasoning") or ""
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"thinking", "reasoning"}:
                thinking += part.get("thinking") or part.get("reasoning") or part.get("text") or ""
    blocks = getattr(chunk, "content_blocks", None) or []
    if not thinking:
        for part in blocks:
            kind = part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
            if kind in {"thinking", "reasoning"}:
                if isinstance(part, dict):
                    thinking += part.get("thinking") or part.get("reasoning") or part.get("text") or ""
                else:
                    thinking += getattr(part, "reasoning", "") or getattr(part, "text", "") or ""
    return thinking


async def _emit_thinking(run_id: str, think_block: str | None, text: str) -> str:
    if not text:
        return think_block or ""
    if think_block is None:
        think_block = new_id()
        await broker.publish(
            run_id,
            "block.started",
            {"block_id": think_block, "block_type": "assistant.thinking", "meta": {}},
        )
    await broker.publish(run_id, "block.delta", {"block_id": think_block, "text": text})
    return think_block


async def _stream_graph(
    run_id: str,
    graph,
    messages: list,
    thinking_level: str = "off",
    recursion_limit: int = 80,
) -> None:
    emit_thinking = thinking_enabled(thinking_level)
    cancel = _cancel[run_id]
    md_block: str | None = None
    think_block: str | None = None
    tool_blocks: dict[str, str] = {}
    got_thought = False
    # After answer/tool content starts, ignore further reasoning so UI order stays
    # thinking → tools/markdown (models often interleave them).
    answer_phase = False

    async def _close_thinking() -> None:
        nonlocal think_block
        if not think_block:
            return
        await broker.publish(run_id, "block.completed", {"block_id": think_block, "status": "ok"})
        think_block = None

    async def _close_markdown() -> None:
        nonlocal md_block
        if not md_block:
            return
        await broker.publish(run_id, "block.completed", {"block_id": md_block, "status": "ok"})
        md_block = None

    async for event in graph.astream_events(
        {"messages": messages},
        version="v2",
        config={"recursion_limit": max(1, recursion_limit)},
    ):
        if cancel.is_set():
            break
        kind = event.get("event")
        data = event.get("data") or {}
        if kind == "on_chat_model_start":
            # Each LLM turn gets its own thinking card. Do not inherit
            # answer_phase from the previous tool/answer burst.
            await _close_thinking()
            await _close_markdown()
            answer_phase = False
            got_thought = False
        elif kind == "on_chat_model_stream":
            chunk = data.get("chunk")
            if chunk is None:
                continue
            content = chunk.content
            text = ""
            thought = _thinking_from_chunk(chunk)
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in {"text", "output_text"}:
                            text += part.get("text") or ""
                    elif isinstance(part, str):
                        text += part
            if thought and emit_thinking and not answer_phase:
                got_thought = True
                think_block = await _emit_thinking(run_id, think_block, thought)
            if text:
                # Ignore leading whitespace so a stray "\\n" does not swallow this
                # turn's thinking (common after tool calls).
                if not text.strip() and md_block is None:
                    continue
                answer_phase = True
                await _close_thinking()
                if md_block is None:
                    md_block = new_id()
                    await broker.publish(
                        run_id,
                        "block.started",
                        {"block_id": md_block, "block_type": "assistant.markdown", "meta": {}},
                    )
                await broker.publish(run_id, "block.delta", {"block_id": md_block, "text": text})
        elif kind == "on_chat_model_end":
            output = data.get("output")
            leftover = _thinking_from_chunk(output)
            if leftover and emit_thinking and not got_thought and not answer_phase:
                think_block = await _emit_thinking(run_id, think_block, leftover)
            got_thought = False
            await _close_thinking()
            await _close_markdown()
            # Next model call in the agent loop may think again
            answer_phase = False
        elif kind == "on_tool_start":
            await _close_thinking()
            await _close_markdown()
            # Close open cards for ordering, but do not keep answer_phase
            # across the next LLM turn (that turn may think again).
            answer_phase = False
            call_id = str(event.get("run_id") or new_id())
            block_id = new_id()
            tool_blocks[call_id] = block_id
            name = event.get("name") or "tool"
            await broker.publish(
                run_id,
                "block.started",
                {
                    "block_id": block_id,
                    "block_type": "tool.call",
                    "meta": {"name": name, "args": data.get("input"), "call_id": call_id},
                },
            )
        elif kind == "on_tool_end":
            call_id = str(event.get("run_id") or "")
            block_id = tool_blocks.get(call_id) or new_id()
            output = data.get("output")
            text = output if isinstance(output, str) else str(output)
            result_id = new_id()
            await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "ok"})
            await broker.publish(
                run_id,
                "block.started",
                {
                    "block_id": result_id,
                    "block_type": "tool.result",
                    "meta": {"name": event.get("name"), "call_id": call_id},
                },
            )
            await broker.publish(run_id, "block.delta", {"block_id": result_id, "text": text[:8000]})
            await broker.publish(run_id, "block.completed", {"block_id": result_id, "status": "ok"})
