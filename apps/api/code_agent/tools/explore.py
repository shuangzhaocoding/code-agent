from __future__ import annotations

import contextvars

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool as lc_tool

from code_agent.plugins.base import registry
from code_agent.tools.context import get_run_id, get_workspace

_exploring: contextvars.ContextVar[bool] = contextvars.ContextVar("exploring", default=False)

READ_TOOL_NAMES = ("read_file", "list_dir", "glob_search", "grep_search")

EXPLORE_PROMPT = """You are a read-only codebase explorer.
Investigate the workspace to answer the goal. You may only read and search.
Do not suggest applying patches or running mutating commands.
When you have enough evidence, stop calling tools and write a concise report:
- What you found
- Key file paths
- Remaining unknowns
Keep the report under 40 lines.
"""


@lc_tool
async def explore_codebase(goal: str, max_steps: int = 6) -> str:
    """Read-only explorer sub-agent. Search/read the repo without editing.

    Use this to map modules, find call sites, or answer "where is X" in parallel with the main task.
    """
    if _exploring.get():
        return "ERROR: nested explore_codebase is not allowed"
    text = (goal or "").strip()
    if not text:
        return "ERROR: goal is required"
    steps = max(1, min(int(max_steps or 6), 12))

    tools = [registry.tools[name].tool for name in READ_TOOL_NAMES if name in registry.tools]
    if not tools:
        return "ERROR: read-only tools are unavailable"

    run_id = get_run_id()
    if not run_id:
        return "ERROR: not in an active run"

    from code_agent.db.models import Conversation, Run
    from code_agent.llm.hub import resolve_chat_model
    from code_agent.protocol.events import new_id
    from code_agent.streaming.broker import broker

    run = await Run.get_or_none(id=run_id)
    if not run:
        return "ERROR: run not found"
    conv = await Conversation.get_or_none(id=run.conversation_id)
    if not conv:
        return "ERROR: conversation not found"
    model, _, _ = await resolve_chat_model(conv.model_id, "off", prefer_tools=True)
    if model is None:
        return "ERROR: model.missing"

    bound = model.bind_tools(tools)
    messages: list = [
        SystemMessage(content=EXPLORE_PROMPT),
        HumanMessage(content=f"Workspace: {get_workspace().get('root_path')}\nGoal: {text}"),
    ]
    token = _exploring.set(True)
    used = 0
    report = ""
    block_id = new_id()
    try:
        await broker.publish(
            run_id,
            "block.started",
            {"block_id": block_id, "block_type": "explore", "meta": {"goal": text, "max_steps": steps}},
        )
        await broker.publish(run_id, "block.delta", {"block_id": block_id, "text": f"探索：{text}\n"})
        for _ in range(steps):
            ai = await bound.ainvoke(messages)
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                report = str(getattr(ai, "content", "") or "")
                break
            for call in tool_calls:
                used += 1
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {}) or {}
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
                tool = next((item for item in tools if item.name == name), None)
                if tool is None:
                    result = f"ERROR: unknown tool {name}"
                else:
                    try:
                        result = await tool.ainvoke(args)
                    except Exception as exc:
                        result = f"ERROR: {exc}"
                messages.append(ToolMessage(content=str(result)[:8000], tool_call_id=call_id or name))
        if not report:
            last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
            report = str(getattr(last, "content", "") or "No findings.")
        summary = report.strip() or "No findings."
        await broker.publish(run_id, "block.delta", {"block_id": block_id, "text": summary})
        await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "ok"})
        return f"Explore report ({used} tool calls):\n{summary}"
    except Exception as exc:
        await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "error"})
        return f"ERROR: {exc}"
    finally:
        _exploring.reset(token)
