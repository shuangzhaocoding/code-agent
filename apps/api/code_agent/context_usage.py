from __future__ import annotations

import json
from typing import Any

from code_agent.db.models import Conversation, Message, Workspace
from code_agent.plugins.base import registry
from code_agent.llm.thinking import normalize_thinking_level, thinking_enabled, thinking_prompt
from code_agent.streaming.run_manager import _system_prompt

CONTEXT_LIMIT = 1_048_576
RECOMMENDED_LIMIT = 128_000
SLIDING_WINDOW_SIZE = 12

CATEGORY_LABELS = {
    "system_prompt": "系统指令",
    "recent_messages": "近期对话",
    "current_user": "当前输入",
    "tools_schema": "工具定义",
    "files": "附件",
}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other_chars = len(text) - ascii_chars
    return max(0, int(round(other_chars / 1.6 + ascii_chars / 4.0)))


def _estimate_tools_tokens(mode: str) -> int:
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


def _category(key: str, tokens: int, chars: int = 0) -> dict[str, Any]:
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
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    level = normalize_thinking_level(thinking_level)
    workspace: Workspace | None = None
    rows: list[Message] = []

    if conversation_id:
        conv = await Conversation.get_or_none(id=conversation_id)
        if conv:
            workspace = await Workspace.get_or_none(id=conv.workspace_id)
            mode = conv.mode or mode
            rows = await Message.filter(conversation_id=conversation_id).order_by("sort_key")

    system_text = ""
    if workspace:
        system_text = _system_prompt(workspace, mode, level)
    else:
        system_text = "You are Code Agent."

    recent_rows = rows[-SLIDING_WINDOW_SIZE:] if rows else []
    recent_text = "\n".join(_message_text(row) for row in recent_rows if _message_text(row))

    current_user = (user_content or "").strip()
    file_tokens = 0
    for item in files or []:
        mime = str(item.get("type") or "")
        size = int(item.get("size") or 0)
        if mime.startswith("image/"):
            file_tokens += max(512, min(4096, size // 800))
        else:
            file_tokens += estimate_tokens(str(item.get("name") or "")) + min(2048, size // 4)

    categories = [
        _category("system_prompt", estimate_tokens(system_text), len(system_text)),
        _category("tools_schema", _estimate_tools_tokens(mode)),
        _category("recent_messages", estimate_tokens(recent_text), len(recent_text)),
    ]
    if current_user:
        categories.append(_category("current_user", estimate_tokens(current_user), len(current_user)))
    if file_tokens:
        categories.append(_category("files", file_tokens))

    total = sum(item["tokens"] for item in categories)
    usage_percent = round((total / CONTEXT_LIMIT) * 100, 2) if CONTEXT_LIMIT else 0.0
    recommended_usage_percent = round((total / RECOMMENDED_LIMIT) * 100, 2) if RECOMMENDED_LIMIT else 0.0

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
            "messages_in_window": len(recent_rows),
            "messages_summarized": max(0, len(rows) - len(recent_rows)),
            "messages_outside_window": max(0, len(rows) - len(recent_rows)),
            "summarize_trigger": 0,
            "sliding_window_size": SLIDING_WINDOW_SIZE,
            "memory_summary_chars": 0,
            "needs_summarize": False,
        },
    }
