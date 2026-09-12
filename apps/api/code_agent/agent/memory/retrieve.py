from __future__ import annotations

import re
from typing import Any

from code_agent.agent.memory.schema import DEFAULT_ALWAYS_INJECT_KINDS
from code_agent.config import settings
from code_agent.db.models import WorkspaceMemory


def _keywords(text: str) -> set[str]:
    parts = re.findall(r"[\w\u4e00-\u9fff]{2,}", (text or "").lower())
    return set(parts)


def _always_inject_kinds() -> set[str]:
    configured = settings.get("agent.memory.always_inject_kinds")
    if isinstance(configured, list) and configured:
        return set(str(k) for k in configured)
    return set(DEFAULT_ALWAYS_INJECT_KINDS)


def memory_source_flag(source: Any, key: str, default: bool) -> bool:
    if not isinstance(source, dict) or key not in source:
        return default
    return bool(source.get(key))


def is_memory_enabled(source: Any) -> bool:
    return memory_source_flag(source, "enabled", True)


def is_memory_pinned(source: Any) -> bool:
    return memory_source_flag(source, "pinned", False)


def select_memories(
    rows: list[Any],
    query: str,
    *,
    max_inject: int,
    always_kinds: set[str],
    always_cap: int,
) -> list[Any]:
    enabled = [row for row in rows if is_memory_enabled(getattr(row, "source", None))]
    if not enabled:
        return []

    pinned = [row for row in enabled if is_memory_pinned(getattr(row, "source", None))]
    always = [row for row in enabled if row not in pinned and getattr(row, "kind", "") in always_kinds][:always_cap]

    keywords = _keywords(query)
    scored: list[tuple[float, Any]] = []
    skip = set(id(row) for row in pinned + always)
    for row in enabled:
        if id(row) in skip:
            continue
        hay = f"{getattr(row, 'subject', '')} {' '.join(getattr(row, 'tags', None) or [])}".lower()
        content = getattr(row, "content", None)
        if isinstance(content, dict):
            hay += " " + str(content.get("statement", "")).lower()
        score = sum(1 for kw in keywords if kw in hay)
        if score > 0:
            scored.append((score, row))
    scored.sort(
        key=lambda x: (
            -x[0],
            -(x[1].updated_at.timestamp() if getattr(x[1], "updated_at", None) else 0),
        )
    )

    picked: list[Any] = list(pinned)
    for row in always:
        if len(picked) >= max_inject:
            break
        if row not in picked:
            picked.append(row)
    for _, row in scored:
        if len(picked) >= max_inject:
            break
        if row not in picked:
            picked.append(row)

    if len(picked) < max_inject:
        for row in enabled:
            if row in picked:
                continue
            if getattr(row, "kind", "") in {
                "decision",
                "bug_fix",
                "lesson",
                "fact",
                "architecture",
                "context",
                "todo",
            }:
                picked.append(row)
            if len(picked) >= max_inject:
                break
    return picked[:max_inject]


async def retrieve_memories(workspace_id: str, query: str, *, limit: int | None = None) -> list[dict]:
    max_inject = limit or int(settings.get("agent.memory.max_inject") or 10)
    rows = await WorkspaceMemory.filter(workspace_id=workspace_id, superseded_by__isnull=True).order_by("-updated_at")
    if not rows:
        return []

    picked = select_memories(
        list(rows),
        query,
        max_inject=max_inject,
        always_kinds=_always_inject_kinds(),
        always_cap=int(settings.get("agent.memory.always_inject_max") or 5),
    )
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "subject": r.subject,
            "content": r.content,
            "tags": r.tags,
            "pinned": is_memory_pinned(r.source),
            "enabled": is_memory_enabled(r.source),
        }
        for r in picked
    ]
