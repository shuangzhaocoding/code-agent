from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Run, Workspace
from code_agent.llm.hub import resolve_chat_model
from code_agent.plugins.base import registry
from code_agent.protocol.events import new_id
from code_agent.skills.registry import list_skill_catalog
from code_agent.streaming.broker import broker
from code_agent.tools.context import set_tool_context
from code_agent.tools.host import register_builtin_tools

_tasks: set[asyncio.Task] = set()
_cancel: dict[str, asyncio.Event] = {}


def _system_prompt(workspace: Workspace, mode: str, thinking: bool = False) -> str:
    skills = list_skill_catalog(workspace.root_path)
    skill_lines = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skills if not s.get("invalid_reason")
    ) or "(none)"
    extra = settings.get("agent.system_prompt_extra") or ""
    return f"""You are Code Agent, a coding assistant working on a real workspace.

Workspace root: {workspace.root_path}
Mode: {mode}
- ask: read-only. Do not write files or run mutating commands.
- plan: propose a numbered plan, wait if the user must confirm.
- agent: you may edit files and run commands inside the workspace.

Rules:
- Prefer search_replace over write_file for existing files.
- Use list_skills / load_skill when a skill matches the task.
- Use git_status / git_diff / git_log for version control; git_commit and git_push require user confirmation.
- Paths are relative to the workspace root. Never escape it.
- Be concise. Show your work via tools rather than dumping huge code in chat.
- After edits, mention which files changed.
{'- Deep thinking is ON. Reason carefully before acting; keep the analysis brief.' if thinking else ''}

Available skills:
{skill_lines}

{extra}
""".strip()


def _history_messages(rows: list[Message]) -> list:
    out = []
    for row in rows:
        text_parts = []
        for block in row.blocks or []:
            if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
                text_parts.append(block["text"])
        text = "\n".join(text_parts).strip()
        if not text:
            continue
        if row.role == "user":
            out.append(HumanMessage(content=text))
        elif row.role == "assistant":
            out.append(AIMessage(content=text))
    return out


async def start_run(
    conversation_id: str,
    user_text: str,
    mode: str,
    model_id: str | None,
    references: list | None,
    thinking: bool = False,
) -> Run:
    conv = await Conversation.get(id=conversation_id)
    last = await Message.filter(conversation_id=conversation_id).order_by("-sort_key").first()
    sort_key = (last.sort_key + 1) if last else 1
    blocks = [{"id": new_id(), "type": "user.text", "text": user_text, "meta": {}, "status": "ok"}]
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
        conv.title = user_text.strip()[:72] or "New chat"
    run = await Run.create(
        conversation_id=conversation_id,
        status="queued",
        mode=mode,
        model_snapshot={"model_id": model_id, "thinking": thinking},
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
    try:
        run.status = "running"
        await run.save(update_fields=["status"])
        await broker.publish(run_id, "run.started", {"mode": run.mode})
        thinking = bool((run.model_snapshot or {}).get("thinking"))
        model, model_row = await resolve_chat_model(conv.model_id, thinking)
        if model is None:
            await _fail(run_id, "model.missing", "没有可用的 LLM。请先在 Models 面板添加 Provider。")
            return
        if model_row and not model_row.supports_tools and run.mode == "agent":
            await _fail(run_id, "model.unsupported_tools", "当前模型不支持工具调用，请改用 Ask 或更换模型。")
            return

        set_tool_context(run_id, {"id": str(workspace.id), "root_path": workspace.root_path})
        tools = registry.enabled_tools(run.mode)
        from langgraph.prebuilt import create_react_agent

        graph = create_react_agent(model, tools, prompt=_system_prompt(workspace, run.mode, thinking))
        history = await Message.filter(conversation_id=conv.id).order_by("sort_key")
        lc_messages = _history_messages(list(history))

        timeout = int(settings.get("agent.run_timeout_sec") or 900)
        await asyncio.wait_for(_stream_graph(run_id, graph, lc_messages, thinking), timeout=timeout)
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


async def _stream_graph(run_id: str, graph, messages: list, thinking: bool = False) -> None:
    del thinking
    cancel = _cancel[run_id]
    md_block: str | None = None
    think_block: str | None = None
    tool_blocks: dict[str, str] = {}
    got_thought = False

    async for event in graph.astream_events({"messages": messages}, version="v2"):
        if cancel.is_set():
            break
        kind = event.get("event")
        data = event.get("data") or {}
        if kind == "on_chat_model_stream":
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
            if thought:
                got_thought = True
                think_block = await _emit_thinking(run_id, think_block, thought)
            if text:
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
            if leftover and not got_thought:
                think_block = await _emit_thinking(run_id, think_block, leftover)
            got_thought = False
            if md_block:
                await broker.publish(run_id, "block.completed", {"block_id": md_block, "status": "ok"})
                md_block = None
            if think_block:
                await broker.publish(run_id, "block.completed", {"block_id": think_block, "status": "ok"})
                think_block = None
        elif kind == "on_tool_start":
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
