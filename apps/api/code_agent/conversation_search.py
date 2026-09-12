from __future__ import annotations

from typing import Any, Iterable

from tortoise import connections

from code_agent.db.models import Conversation, Message

SEARCHABLE_BLOCK_TYPES = {
    "user.text",
    "assistant.markdown",
    "assistant.plan",
    "todo",
    "error",
}


def like_escape(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def block_search_text(blocks: Iterable[Any]) -> str:
    parts: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "")
        text = str(block.get("text") or "").strip()
        if btype in SEARCHABLE_BLOCK_TYPES and text:
            parts.append(text)
            continue
        meta = block.get("meta") if isinstance(block.get("meta"), dict) else {}
        path = str(meta.get("path") or "").strip()
        if path:
            parts.append(path)
    return "\n".join(parts)


def make_snippet(text: str, query: str, radius: int = 42) -> str:
    hay = " ".join((text or "").split())
    needle = " ".join((query or "").split())
    if not hay:
        return ""
    if not needle:
        return hay[:80]
    lower = hay.lower()
    idx = lower.find(needle.lower())
    if idx < 0:
        return hay[:80]
    start = max(0, idx - radius)
    end = min(len(hay), idx + len(needle) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(hay) else ""
    return prefix + hay[start:end] + suffix


def _dialect() -> str:
    try:
        conn = connections.get("default")
        return str(getattr(getattr(conn, "capabilities", None), "dialect", "") or "sqlite")
    except Exception:
        return "sqlite"


async def conversation_ids_matching_content(workspace_id: str, query: str) -> set[str]:
    needle = like_escape(query.strip())
    if not needle:
        return set()
    dialect = _dialect()
    conn = connections.get("default")
    pattern = f"%{needle}%"
    if dialect == "postgres":
        sql = """
            SELECT DISTINCT m.conversation_id::text AS conversation_id
            FROM messages m
            INNER JOIN conversations c ON c.id = m.conversation_id
            WHERE c.workspace_id = $1
              AND m.blocks::text ILIKE $2 ESCAPE '\\'
        """
        rows = await conn.execute_query_dict(sql, [workspace_id, pattern])
    else:
        sql = """
            SELECT DISTINCT m.conversation_id AS conversation_id
            FROM messages m
            INNER JOIN conversations c ON c.id = m.conversation_id
            WHERE c.workspace_id = ?
              AND CAST(m.blocks AS TEXT) LIKE ? ESCAPE '\\'
        """
        rows = await conn.execute_query_dict(sql, [workspace_id, pattern])
    out: set[str] = set()
    for row in rows:
        cid = row.get("conversation_id")
        if cid is not None:
            out.add(str(cid))
    return out


async def snippets_for_conversations(conv_ids: list[str], query: str) -> dict[str, str]:
    if not conv_ids or not query.strip():
        return {}
    rows = await Message.filter(conversation_id__in=conv_ids).order_by("sort_key")
    found: dict[str, str] = {}
    q = query.strip().lower()
    for row in rows:
        cid = str(row.conversation_id)
        if cid in found:
            continue
        text = block_search_text(row.blocks or [])
        if q in text.lower():
            found[cid] = make_snippet(text, query)
    return found


async def search_conversations(
    workspace_id: str,
    *,
    query: str = "",
    archived: str = "exclude",
    limit: int = 200,
) -> list[Conversation]:
    archived_mode = (archived or "exclude").strip().lower()
    qs = Conversation.filter(workspace_id=workspace_id)
    if archived_mode == "only":
        qs = qs.filter(archived=True)
    elif archived_mode != "include":
        qs = qs.filter(archived=False)

    q = (query or "").strip()
    if not q:
        return await qs.order_by("-updated_at").limit(limit)

    title_qs = qs.filter(title__icontains=q)
    title_rows = await title_qs
    title_ids = {str(row.id) for row in title_rows}

    content_ids = await conversation_ids_matching_content(workspace_id, q)
    wanted = title_ids | content_ids
    if not wanted:
        return []

    rows = await Conversation.filter(id__in=list(wanted), workspace_id=workspace_id)
    if archived_mode == "only":
        rows = [row for row in rows if row.archived]
    elif archived_mode != "include":
        rows = [row for row in rows if not row.archived]
    rows.sort(key=lambda row: row.updated_at or row.created_at, reverse=True)
    return rows[:limit]
