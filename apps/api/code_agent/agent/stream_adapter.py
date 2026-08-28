from __future__ import annotations

from code_agent.llm.thinking import thinking_enabled
from code_agent.protocol.events import new_id
from code_agent.streaming.broker import broker

# Only the user-facing ReAct loop should emit SSE blocks.
_STREAM_NODES = frozenset({"agent"})


def _graph_node(event: dict) -> str:
    meta = event.get("metadata") or {}
    return str(meta.get("langgraph_node") or "")


def _should_stream_llm(event: dict) -> bool:
    node = _graph_node(event)
    return not node or node in _STREAM_NODES


def thinking_from_chunk(chunk) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, (list, tuple)):
        return "".join(thinking_from_chunk(item) for item in chunk)
    msg = getattr(chunk, "message", None)
    if msg is not None and msg is not chunk:
        inner = thinking_from_chunk(msg)
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


async def emit_thinking(run_id: str, think_block: str | None, text: str) -> str:
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


async def stream_graph_events(
    run_id: str,
    graph,
    input_state: dict,
    config: dict,
    *,
    thinking_level: str = "off",
    cancel_event,
) -> None:
    emit_thinking_blocks = thinking_enabled(thinking_level)
    md_block: str | None = None
    think_block: str | None = None
    tool_blocks: dict[str, str] = {}
    got_thought = False
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

    async for event in graph.astream_events(input_state, version="v2", config=config):
        if cancel_event.is_set():
            break
        kind = event.get("event")
        data = event.get("data") or {}
        if kind in {"on_chat_model_start", "on_chat_model_stream", "on_chat_model_end"}:
            if not _should_stream_llm(event):
                continue
        if kind == "on_chat_model_start":
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
            thought = thinking_from_chunk(chunk)
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in {"text", "output_text"}:
                            text += part.get("text") or ""
                    elif isinstance(part, str):
                        text += part
            if thought and emit_thinking_blocks and not answer_phase:
                got_thought = True
                think_block = await emit_thinking(run_id, think_block, thought)
            if text:
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
            leftover = thinking_from_chunk(output)
            if leftover and emit_thinking_blocks and not got_thought and not answer_phase:
                think_block = await emit_thinking(run_id, think_block, leftover)
            got_thought = False
            await _close_thinking()
            await _close_markdown()
            answer_phase = False
        elif kind == "on_tool_start":
            await _close_thinking()
            await _close_markdown()
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

    await _close_thinking()
    await _close_markdown()
