from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from code_agent.agent.memory.heuristics import heuristic_memories
from code_agent.agent.memory.schema import MEMORY_KINDS, build_extract_prompt
from code_agent.config import settings
from code_agent.db.models import Conversation, Message, Run, WorkspaceMemory


def _rows_to_text(rows: list[Message]) -> str:
    parts: list[str] = []
    for row in rows:
        role = row.role
        texts = []
        for block in row.blocks or []:
            if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
                texts.append(str(block["text"])[:2000])
        if texts:
            parts.append(f"{role}: " + "\n".join(texts))
    return "\n\n".join(parts)


def _parse_llm_json(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _dedupe_key(item: dict) -> tuple[str, str]:
    return (str(item.get("kind") or ""), str(item.get("subject") or "").strip().lower())


async def _upsert_memory(
    *,
    workspace_id: str,
    conversation_id: str,
    run_id: str,
    item: dict,
    auto_kinds: set[str],
) -> WorkspaceMemory | None:
    kind = str(item.get("kind") or "decision")
    if kind not in auto_kinds and kind not in MEMORY_KINDS:
        return None
    if kind not in auto_kinds:
        return None
    subject = str(item.get("subject") or "").strip()[:200]
    statement = str(item.get("statement") or "").strip()
    if not subject or not statement:
        return None
    existing = await WorkspaceMemory.filter(
        workspace_id=workspace_id, kind=kind, subject=subject, superseded_by__isnull=True
    ).first()
    content: dict[str, Any] = {
        "statement": statement,
        "related_paths": item.get("related_paths") or [],
    }
    source = {"conversation_id": conversation_id, "run_id": run_id}
    if existing:
        existing.content = content
        existing.tags = item.get("tags") or existing.tags
        existing.source = source
        await existing.save(update_fields=["content", "tags", "source", "updated_at"])
        return existing
    return await WorkspaceMemory.create(
        workspace_id=workspace_id,
        kind=kind,
        subject=subject,
        content=content,
        tags=item.get("tags") or [],
        source=source,
    )


async def compress_conversation_summary(conversation_id: str, outside_rows: list[Message], model) -> str:
    conv = await Conversation.get(id=conversation_id)
    existing = (conv.summary or "").strip()
    chunk = _rows_to_text(outside_rows)
    if not chunk.strip():
        return existing
    prompt = f"""Summarize the following older conversation turns into concise bullet points for future context.
Preserve decisions, file paths, conventions, and unresolved tasks. Use the same language as the conversation.

Existing summary:
{existing or "(none)"}

New turns to merge:
{chunk}

Output only the updated summary (bullet points, no preamble)."""
    response = await model.ainvoke([SystemMessage(content="You compress chat history."), HumanMessage(content=prompt)])
    text = response.content if isinstance(response.content, str) else str(response.content)
    return text.strip()


async def extract_workspace_memories(
    *,
    workspace_id: str,
    conversation_id: str,
    run_id: str,
    model,
    rows: list[Message] | None = None,
) -> list[WorkspaceMemory]:
    if not settings.get("agent.memory.enabled", True):
        return []
    max_extract = int(settings.get("agent.memory.extract_per_run") or 5)
    auto_kinds = set(
        settings.get("agent.memory.auto_kinds")
        or [
            "profile",
            "preference",
            "goal",
            "context",
            "workflow",
            "decision",
            "architecture",
            "convention",
            "fact",
            "bug_fix",
            "lesson",
            "dependency",
            "todo",
        ]
    )

    if rows is None:
        run = await Run.get(id=run_id)
        rows = await Message.filter(conversation_id=run.conversation_id, run_id=run_id).order_by("sort_key")
    if not rows:
        return []

    text = _rows_to_text(rows)[-8000:]
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in heuristic_memories(text):
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    llm_slots = max(0, max_extract - len(merged))
    if llm_slots > 0:
        prompt = build_extract_prompt(max_extract=llm_slots, conversation_text=text)
        response = await model.ainvoke(
            [SystemMessage(content="Return valid JSON only."), HumanMessage(content=prompt)]
        )
        raw = response.content if isinstance(response.content, str) else str(response.content)
        for item in _parse_llm_json(raw):
            key = _dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_extract:
                break

    created: list[WorkspaceMemory] = []
    for item in merged[:max_extract]:
        row = await _upsert_memory(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            run_id=run_id,
            item=item,
            auto_kinds=auto_kinds,
        )
        if row:
            created.append(row)
    return created
