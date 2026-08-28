from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Workspace
from code_agent.agent.prompt import build_system_prompt
from code_agent.agent.memory.retrieve import retrieve_memories
from code_agent.llm.vision import build_user_content, message_files, message_text


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other_chars = len(text) - ascii_chars
    return max(0, int(round(other_chars / 1.6 + ascii_chars / 4.0)))


def sliding_window_size() -> int:
    return int(settings.get("agent.sliding_window_size") or 12)


def compress_threshold_tokens() -> int:
    return int(settings.get("agent.compress_threshold_tokens") or 90000)


def _message_text(row: Message) -> str:
    parts: list[str] = []
    for block in row.blocks or []:
        if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def history_to_lc_messages(rows: list[Message], *, vision: bool = False) -> list:
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


async def load_conversation_rows(conversation_id: str) -> list[Message]:
    return await Message.filter(conversation_id=conversation_id).order_by("sort_key")


def split_window(rows: list[Message], *, window_size: int | None = None) -> tuple[list[Message], list[Message], bool]:
    size = window_size or sliding_window_size()
    if len(rows) <= size:
        return rows, [], False
    outside = rows[:-size]
    inside = rows[-size:]
    return inside, outside, True


def estimate_messages_tokens(rows: list[Message]) -> int:
    return estimate_tokens("\n".join(_message_text(r) for r in rows if _message_text(r)))


async def build_run_context(
    *,
    workspace: Workspace,
    conversation: Conversation,
    mode: str,
    thinking_level: str,
    vision: bool,
    need_vision: bool,
    skill_name: str | None = None,
    skill_body: str | None = None,
    user_query: str = "",
) -> dict[str, Any]:
    rows = await load_conversation_rows(str(conversation.id))
    inside, outside, has_outside = split_window(rows)
    summary = conversation.summary or ""
    covers = int(conversation.summary_covers_sort_key or 0)
    outside_uncovered = [r for r in outside if r.sort_key > covers]
    needs_compress = bool(outside_uncovered) or (
        estimate_messages_tokens(inside) > compress_threshold_tokens()
    )

    memory_facts: list[dict] = []
    if settings.get("agent.memory.enabled", True):
        memory_facts = await retrieve_memories(str(workspace.id), user_query or message_text(rows[-1].blocks if rows else []))

    system = build_system_prompt(
        workspace,
        mode,
        thinking_level,
        skill_name=skill_name,
        skill_body=skill_body,
        memory_facts=memory_facts,
        conversation_summary=summary,
    )
    lc_messages = [SystemMessage(content=system)] + history_to_lc_messages(
        inside, vision=vision and need_vision
    )
    return {
        "messages": lc_messages,
        "system_prompt": system,
        "memory_facts": memory_facts,
        "conversation_summary": summary,
        "needs_compress": needs_compress,
        "outside_rows": outside_uncovered,
        "window_rows": inside,
        "window_message_ids": [str(r.id) for r in inside],
        "token_estimate": estimate_tokens(system) + estimate_messages_tokens(inside),
    }
