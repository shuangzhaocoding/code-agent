from __future__ import annotations

import re

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


async def retrieve_memories(workspace_id: str, query: str, *, limit: int | None = None) -> list[dict]:
    max_inject = limit or int(settings.get("agent.memory.max_inject") or 10)
    rows = await WorkspaceMemory.filter(workspace_id=workspace_id, superseded_by__isnull=True).order_by("-updated_at")
    if not rows:
        return []

    always_kinds = _always_inject_kinds()
    always_cap = int(settings.get("agent.memory.always_inject_max") or 5)
    always = [r for r in rows if r.kind in always_kinds][:always_cap]

    keywords = _keywords(query)
    scored: list[tuple[float, WorkspaceMemory]] = []
    for row in rows:
        if row in always:
            continue
        hay = f"{row.subject} {' '.join(row.tags or [])}".lower()
        if isinstance(row.content, dict):
            hay += " " + str(row.content.get("statement", "")).lower()
        score = sum(1 for kw in keywords if kw in hay)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], -x[1].updated_at.timestamp() if x[1].updated_at else 0))

    picked: list[WorkspaceMemory] = list(always)
    for _, row in scored:
        if len(picked) >= max_inject:
            break
        if row not in picked:
            picked.append(row)

    if len(picked) < max_inject:
        for row in rows:
            if row in picked:
                continue
            if row.kind in {"decision", "bug_fix", "lesson", "fact", "architecture", "context", "todo"}:
                picked.append(row)
            if len(picked) >= max_inject:
                break

    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "subject": r.subject,
            "content": r.content,
            "tags": r.tags,
        }
        for r in picked[:max_inject]
    ]
