from __future__ import annotations

import json
from typing import Any

TODO_STATUSES = ("pending", "in_progress", "completed", "cancelled")


def _as_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"todos must be a JSON array: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("todos must be a JSON array of objects")
        return parsed
    raise ValueError("todos must be an array")


def normalize_todos(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    in_progress = 0
    for index, row in enumerate(_as_list(raw), start=1):
        if isinstance(row, str):
            content = row.strip()
            status = "pending"
            ident = str(index)
        elif isinstance(row, dict):
            content = str(row.get("content") or row.get("text") or row.get("title") or "").strip()
            status = str(row.get("status") or "pending").strip().lower().replace(" ", "_")
            ident = str(row.get("id") or index)
        else:
            continue
        if status in {"done", "complete", "finished"}:
            status = "completed"
        if status in {"doing", "active", "progress"}:
            status = "in_progress"
        if status in {"canceled", "cancel", "skipped"}:
            status = "cancelled"
        if status not in TODO_STATUSES:
            status = "pending"
        if not content:
            continue
        if status == "in_progress":
            in_progress += 1
            if in_progress > 1:
                status = "pending"
        items.append({"id": ident[:80], "content": content[:500], "status": status})
    return items[:30]


def render_todo_text(items: list[dict[str, str]]) -> str:
    marks = {
        "pending": "[ ]",
        "in_progress": "[>]",
        "completed": "[x]",
        "cancelled": "[-]",
    }
    if not items:
        return "(empty todo list)"
    lines = []
    for item in items:
        mark = marks.get(item["status"], "[ ]")
        lines.append(f"{mark} {item['content']}")
    return "\n".join(lines)


def todo_summary(items: list[dict[str, str]]) -> dict[str, int]:
    out = {key: 0 for key in TODO_STATUSES}
    for item in items:
        out[item["status"]] = out.get(item["status"], 0) + 1
    out["total"] = len(items)
    return out
