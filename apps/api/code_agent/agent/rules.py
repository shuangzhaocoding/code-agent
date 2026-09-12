from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from code_agent.config import settings

RULE_ROOT_FILES = ("AGENTS.md", "agents.md")
RULE_DIR = ".code-agent/rules"
RULES_STATE_REL = ".code-agent/rules-state.json"
MAX_RULE_FILES = 24
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    raw = text or ""
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw.strip()
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, raw[match.end() :].strip()


def format_rule_section(path: str, body: str, *, title: str = "") -> str:
    heading = title.strip() or path
    content = body.strip()
    if not content:
        return ""
    return f"### {heading}\nPath: {path}\n\n{content}"


def assemble_rules_prompt(sections: list[str], *, max_chars: int) -> str:
    kept: list[str] = []
    used = 0
    truncated = False
    for section in sections:
        text = section.strip()
        if not text:
            continue
        extra = len(text) + (2 if kept else 0)
        if kept and used + extra > max_chars:
            truncated = True
            break
        if not kept and len(text) > max_chars:
            kept.append(text[: max(0, max_chars - 80)].rstrip() + "\n\n[workspace rules truncated]")
            truncated = True
            break
        kept.append(text)
        used += extra
    if not kept:
        return ""
    body = "\n\n".join(kept)
    if truncated and not body.endswith("[workspace rules truncated]"):
        body += "\n\n[workspace rules truncated]"
    return body


def rules_max_chars() -> int:
    try:
        return max(1000, int(settings.get("agent.rules_max_chars") or 12000))
    except (TypeError, ValueError):
        return 12000


async def _read_text(fs: Any, rel: str) -> str | None:
    try:
        if not await fs.is_file(rel):
            return None
        return await fs.read_text(rel)
    except HTTPException:
        return None
    except Exception:
        return None


async def _list_rule_files(fs: Any) -> list[str]:
    try:
        if not await fs.is_dir(RULE_DIR):
            return []
        items = await fs.list_dir(RULE_DIR)
    except HTTPException:
        return []
    except Exception:
        return []
    names: list[str] = []
    for item in items:
        if item.get("is_dir"):
            continue
        name = str(item.get("name") or "")
        path = str(item.get("path") or f"{RULE_DIR}/{name}").replace("\\", "/")
        lower = name.lower()
        if lower.endswith(".md") or lower.endswith(".mdc"):
            names.append(path)
    names.sort(key=str.lower)
    return names[:MAX_RULE_FILES]


def empty_rules_state() -> dict[str, list[str]]:
    return {"disabled": [], "pinned": []}


def normalize_rules_state(raw: Any) -> dict[str, list[str]]:
    data = raw if isinstance(raw, dict) else {}
    disabled = [str(x) for x in (data.get("disabled") or []) if str(x).strip()]
    pinned = [str(x) for x in (data.get("pinned") or []) if str(x).strip()]
    return {"disabled": disabled, "pinned": pinned}


def parse_rules_state(text: str) -> dict[str, list[str]]:
    import json

    try:
        raw = json.loads(text or "{}")
    except Exception:
        return empty_rules_state()
    return normalize_rules_state(raw)


def dump_rules_state(state: dict[str, list[str]]) -> str:
    import json

    return json.dumps(normalize_rules_state(state), ensure_ascii=False, indent=2) + "\n"


def apply_rules_state(entries: list[dict[str, Any]], state: dict[str, list[str]]) -> list[dict[str, Any]]:
    disabled = set(state.get("disabled") or [])
    pinned = set(state.get("pinned") or [])
    active = [item for item in entries if item["path"] not in disabled]
    pinned_items = [item for item in active if item["path"] in pinned]
    rest = [item for item in active if item["path"] not in pinned]
    return pinned_items + rest


async def load_rules_state(fs: Any) -> dict[str, list[str]]:
    text = await _read_text(fs, RULES_STATE_REL)
    if text is None:
        return empty_rules_state()
    return parse_rules_state(text)


async def save_rules_state(fs: Any, state: dict[str, list[str]]) -> dict[str, list[str]]:
    normalized = normalize_rules_state(state)
    await fs.write_text(RULES_STATE_REL, dump_rules_state(normalized))
    return normalized


async def collect_rule_entries(fs: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in RULE_ROOT_FILES:
        text = await _read_text(fs, name)
        if text is None:
            continue
        meta, body = split_frontmatter(text)
        title = meta.get("title") or "AGENTS.md"
        section = format_rule_section(name, body, title=title)
        if section:
            entries.append({"path": name, "title": title, "section": section, "root": True})
        break

    for path in await _list_rule_files(fs):
        text = await _read_text(fs, path)
        if text is None:
            continue
        meta, body = split_frontmatter(text)
        title = meta.get("title") or path.rsplit("/", 1)[-1]
        section = format_rule_section(path, body, title=title)
        if section:
            entries.append({"path": path, "title": title, "section": section, "root": False})
    return entries


async def list_workspace_rules(fs: Any) -> list[dict[str, Any]]:
    state = await load_rules_state(fs)
    disabled = set(state.get("disabled") or [])
    pinned = set(state.get("pinned") or [])
    out: list[dict[str, Any]] = []
    for item in await collect_rule_entries(fs):
        path = item["path"]
        out.append(
            {
                "path": path,
                "title": item["title"],
                "root": bool(item.get("root")),
                "enabled": path not in disabled,
                "pinned": path in pinned,
            }
        )
    return out


async def patch_workspace_rule(fs: Any, path: str, *, enabled: bool | None = None, pinned: bool | None = None) -> dict[str, Any]:
    target = str(path or "").replace("\\", "/").strip()
    if not target:
        raise HTTPException(status_code=400, detail={"code": "rules.path_required"})
    entries = await collect_rule_entries(fs)
    if target not in {item["path"] for item in entries}:
        raise HTTPException(status_code=404, detail={"code": "rules.not_found"})
    state = await load_rules_state(fs)
    disabled = set(state.get("disabled") or [])
    pinned_set = set(state.get("pinned") or [])
    if enabled is False:
        disabled.add(target)
    elif enabled is True:
        disabled.discard(target)
    if pinned is True:
        pinned_set.add(target)
    elif pinned is False:
        pinned_set.discard(target)
    await save_rules_state(fs, {"disabled": sorted(disabled), "pinned": sorted(pinned_set)})
    items = await list_workspace_rules(fs)
    return next(item for item in items if item["path"] == target)


async def load_rules_from_backend(fs: Any, *, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else rules_max_chars()
    state = await load_rules_state(fs)
    entries = apply_rules_state(await collect_rule_entries(fs), state)
    sections = [str(item.get("section") or "") for item in entries]
    return assemble_rules_prompt(sections, max_chars=limit)


async def load_workspace_rules(workspace: Any, *, max_chars: int | None = None) -> str:
    from code_agent.workspace.backend import get_workspace_backend
    from code_agent.workspace.local import LocalWorkspaceBackend

    try:
        fs = await get_workspace_backend(workspace)
    except Exception:
        fs = LocalWorkspaceBackend(workspace)
    try:
        return await load_rules_from_backend(fs, max_chars=max_chars)
    finally:
        close = getattr(fs, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass
