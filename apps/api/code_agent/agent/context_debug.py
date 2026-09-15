"""Build structured context-injection debug payloads for a run."""

from __future__ import annotations

from typing import Any

from code_agent.agent.rules import (
    RULES_STATE_REL,
    apply_rules_state,
    assemble_rules_prompt,
    collect_rule_entries,
    load_rules_state,
    rules_max_chars,
)
from code_agent.skills.registry import list_skill_catalog


async def build_rules_debug(workspace: Any) -> tuple[str, dict[str, Any]]:
    """Return (prompt text, debug dict) for workspace rules."""
    from code_agent.workspace.backend import get_workspace_backend
    from code_agent.workspace.local import LocalWorkspaceBackend

    try:
        fs = await get_workspace_backend(workspace)
    except Exception:
        fs = LocalWorkspaceBackend(workspace)
    try:
        state = await load_rules_state(fs)
        all_entries = await collect_rule_entries(fs)
        disabled = set(state.get("disabled") or [])
        pinned = set(state.get("pinned") or [])
        active = apply_rules_state(all_entries, state)
        limit = rules_max_chars()
        sections = [str(item.get("section") or "") for item in active]
        prompt = assemble_rules_prompt(sections, max_chars=limit)
        truncated = "[workspace rules truncated]" in prompt

        injected_paths: set[str] = set()
        used = 0
        for item in active:
            section = str(item.get("section") or "").strip()
            if not section:
                continue
            extra = len(section) + (2 if injected_paths else 0)
            if injected_paths and used + extra > limit:
                break
            if not injected_paths and len(section) > limit:
                injected_paths.add(item["path"])
                break
            injected_paths.add(item["path"])
            used += extra

        rules_injected = []
        rules_omitted = []
        for item in all_entries:
            path = item["path"]
            row = {
                "path": path,
                "title": item.get("title") or path,
                "root": bool(item.get("root")),
                "pinned": path in pinned,
                "chars": len(str(item.get("section") or "")),
            }
            if path in disabled:
                rules_omitted.append({**row, "reason": "disabled"})
            elif path in injected_paths:
                rules_injected.append({**row, "injected": True})
            else:
                rules_omitted.append({**row, "reason": "truncated" if truncated else "skipped"})

        return prompt, {
            "injected": rules_injected,
            "omitted": rules_omitted,
            "truncated": truncated,
            "max_chars": limit,
            "state_file": RULES_STATE_REL,
        }
    finally:
        close = getattr(fs, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass


def build_skills_catalog_debug(workspace: Any) -> list[dict[str, Any]]:
    out = []
    for s in list_skill_catalog(workspace):
        if s.get("invalid_reason"):
            continue
        out.append(
            {
                "name": s["name"],
                "description": (s.get("description") or "")[:200],
                "source": s.get("source"),
                "path": s.get("path"),
            }
        )
    return out


def build_memories_debug(memory_facts: list[dict] | None) -> list[dict[str, Any]]:
    out = []
    for fact in memory_facts or []:
        content = fact.get("content") or {}
        statement = content.get("statement") if isinstance(content, dict) else str(content)
        out.append(
            {
                "id": str(fact.get("id") or ""),
                "kind": fact.get("kind") or "note",
                "subject": fact.get("subject") or "",
                "pinned": bool(fact.get("pinned")),
                "statement": (statement or "")[:240],
            }
        )
    return out


def build_context_debug(
    *,
    mode: str,
    thinking_level: str,
    rules_debug: dict[str, Any],
    skills_catalog: list[dict[str, Any]],
    memory_facts: list[dict] | None,
    conversation_summary: str,
    skill_name: str | None,
    skill_body: str | None,
    skill_source: str | None = None,
    window_message_ids: list[str] | None = None,
    token_estimate: int = 0,
    needs_compress: bool = False,
) -> dict[str, Any]:
    active_skill = None
    if skill_name and skill_body:
        active_skill = {
            "name": skill_name,
            "source": skill_source or "user_mention",
            "reason": "User @-selected this skill for the turn; full body injected into system prompt.",
            "chars": len(skill_body),
        }
    return {
        "mode": mode,
        "thinking_level": thinking_level,
        "rules": rules_debug,
        "skills_catalog": skills_catalog,
        "active_skill": active_skill,
        "skills_loaded": [],  # filled when agent calls load_skill mid-run
        "memories": build_memories_debug(memory_facts),
        "conversation_summary": {
            "present": bool((conversation_summary or "").strip()),
            "chars": len(conversation_summary or ""),
        },
        "window": {
            "message_count": len(window_message_ids or []),
            "message_ids": list(window_message_ids or []),
            "token_estimate": token_estimate,
            "needs_compress": needs_compress,
        },
    }


async def persist_context_debug(run_id: str, debug: dict[str, Any]) -> None:
    from code_agent.db.models import Run

    run = await Run.get_or_none(id=run_id)
    if not run:
        return
    snapshot = dict(run.model_snapshot or {})
    snapshot["context_debug"] = debug
    run.model_snapshot = snapshot
    await run.save(update_fields=["model_snapshot"])


async def append_skill_loaded(run_id: str, entry: dict[str, Any]) -> None:
    from code_agent.db.models import Run

    run = await Run.get_or_none(id=run_id)
    if not run:
        return
    snapshot = dict(run.model_snapshot or {})
    debug = dict(snapshot.get("context_debug") or {})
    loaded = list(debug.get("skills_loaded") or [])
    name = entry.get("name")
    if name and any(x.get("name") == name for x in loaded):
        return
    loaded.append(entry)
    debug["skills_loaded"] = loaded
    snapshot["context_debug"] = debug
    run.model_snapshot = snapshot
    await run.save(update_fields=["model_snapshot"])
