from __future__ import annotations

from code_agent.agent.context_builder import (
    estimate_tokens,
    load_conversation_rows,
    sliding_window_size,
    split_window,
)
from code_agent.agent.prompt import build_system_prompt
from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Workspace
from code_agent.llm.thinking import normalize_thinking_level, thinking_enabled
from code_agent.llm.vision import IMAGE_TOKEN_ESTIMATE
from code_agent.plugins.base import registry

CONTEXT_LIMIT = 1_048_576
RECOMMENDED_LIMIT = 128_000

CATEGORY_LABELS = {
    "system_prompt": "系统指令",
    "recent_messages": "近期对话",
    "memory_summary": "会话摘要",
    "workspace_memory": "工作区记忆",
    "current_user": "当前输入",
    "tools_schema": "工具定义",
    "files": "附件",
}


def _estimate_tools_tokens(mode: str) -> int:
    import json

    tools = []
    for spec in registry.tools.values():
        if not spec.enabled or mode not in spec.modes:
            continue
        if mode == "ask" and spec.name in {"write_file", "search_replace", "run_command", "delete_file"}:
            continue
        tools.append({"name": spec.name, "description": spec.description or ""})
    return estimate_tokens(json.dumps(tools, ensure_ascii=False))


def _message_text(row: Message) -> str:
    parts: list[str] = []
    for block in row.blocks or []:
        if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def _usage_level(usage_percent: float, recommended_percent: float) -> str:
    if recommended_percent >= 90:
        return "critical"
    if recommended_percent >= 75:
        return "danger"
    if recommended_percent >= 55 or usage_percent >= 80:
        return "warning"
    return "normal"


def _category(key: str, tokens: int, chars: int = 0) -> dict:
    return {
        "key": key,
        "label": CATEGORY_LABELS.get(key, key),
        "tokens": tokens,
        "chars": chars or tokens * 3,
    }


async def compute_context_usage(
    *,
    conversation_id: str | None,
    user_content: str,
    thinking_level: str = "off",
    mode: str = "agent",
    files: list[dict] | None = None,
) -> dict:
    level = normalize_thinking_level(thinking_level)
    workspace: Workspace | None = None
    rows: list[Message] = []
    conversation: Conversation | None = None

    if conversation_id:
        conversation = await Conversation.get_or_none(id=conversation_id)
        if conversation:
            workspace = await Workspace.get_or_none(id=conversation.workspace_id)
            mode = conversation.mode or mode
            rows = await load_conversation_rows(conversation_id)

    inside, outside, _ = split_window(rows, window_size=sliding_window_size())
    recent_text = "\n".join(_message_text(row) for row in inside if _message_text(row))
    summary_text = (conversation.summary or "") if conversation else ""

    memory_facts = []
    memory_text = ""
    if workspace and settings.get("agent.memory.enabled", True):
        from code_agent.agent.memory.retrieve import retrieve_memories

        memory_facts = await retrieve_memories(str(workspace.id), user_content or recent_text)
        memory_text = "\n".join(
            f"{f.get('subject')}: {(f.get('content') or {}).get('statement', '')}" for f in memory_facts
        )

    system_text = ""
    if workspace:
        system_text = build_system_prompt(
            workspace,
            mode,
            level,
            memory_facts=memory_facts,
            conversation_summary=summary_text,
        )
    else:
        system_text = "You are Code Agent."

    current_user = (user_content or "").strip()
    file_tokens = 0
    for item in files or []:
        mime = str(item.get("type") or "")
        size = int(item.get("size") or 0)
        if mime.startswith("image/"):
            file_tokens += IMAGE_TOKEN_ESTIMATE
        else:
            file_tokens += estimate_tokens(str(item.get("name") or "")) + min(2048, size // 4)

    categories = [
        _category("system_prompt", estimate_tokens(system_text), len(system_text)),
        _category("tools_schema", _estimate_tools_tokens(mode)),
        _category("recent_messages", estimate_tokens(recent_text), len(recent_text)),
    ]
    if summary_text:
        categories.append(_category("memory_summary", estimate_tokens(summary_text), len(summary_text)))
    if memory_text:
        categories.append(_category("workspace_memory", estimate_tokens(memory_text), len(memory_text)))
    if current_user:
        categories.append(_category("current_user", estimate_tokens(current_user), len(current_user)))
    if file_tokens:
        categories.append(_category("files", file_tokens))

    total = sum(item["tokens"] for item in categories)
    usage_percent = round((total / CONTEXT_LIMIT) * 100, 2) if CONTEXT_LIMIT else 0.0
    recommended_usage_percent = round((total / RECOMMENDED_LIMIT) * 100, 2) if RECOMMENDED_LIMIT else 0.0
    summarized = max(0, len(outside))
    if conversation and conversation.summary_covers_sort_key:
        summarized = max(0, len([r for r in outside if r.sort_key > conversation.summary_covers_sort_key]))

    return {
        "context_limit": CONTEXT_LIMIT,
        "recommended_limit": RECOMMENDED_LIMIT,
        "mode": mode,
        "thinking": thinking_enabled(level),
        "thinking_level": level,
        "categories": [item for item in categories if item["tokens"] > 0],
        "total_estimated_input": total,
        "session_context_tokens": total,
        "peak_input_tokens": total,
        "usage_percent": usage_percent,
        "recommended_usage_percent": recommended_usage_percent,
        "level": _usage_level(usage_percent, recommended_usage_percent),
        "estimation_method": "heuristic",
        "session_stats": {
            "messages_in_db": len(rows),
            "messages_in_window": len(inside),
            "messages_summarized": summarized,
            "messages_outside_window": len(outside),
            "summarize_trigger": compress_threshold(),
            "sliding_window_size": sliding_window_size(),
            "memory_summary_chars": len(summary_text),
            "needs_summarize": summarized > 0,
        },
    }


def compress_threshold() -> int:
    from code_agent.agent.context_builder import compress_threshold_tokens

    return compress_threshold_tokens()
