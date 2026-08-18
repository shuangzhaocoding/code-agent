from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from code_agent.config import settings

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _parse_skill_md(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    name = str(meta.get("name") or "")
    desc = str(meta.get("description") or "")
    reason = None
    if not NAME_RE.match(name) or len(name) > 64:
        reason = "invalid name"
    if not desc or len(desc) > 1024:
        reason = "invalid description"
    if name != path.parent.name:
        reason = "name must match directory"
    checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
    return {
        "name": name,
        "description": desc,
        "body": body,
        "path": str(path.parent),
        "checksum": checksum,
        "invalid_reason": reason,
        "license": meta.get("license"),
        "metadata": meta.get("metadata") or {},
    }


def skill_roots(workspace_root: str | None = None) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = [
        ("bundled", settings.repo_root / "skills"),
        ("user", Path(settings.get("paths.user_skills", "~/.code-agent/skills")).expanduser()),
    ]
    if workspace_root:
        ws = Path(workspace_root)
        roots.extend(
            [
                ("cursor", ws / ".cursor" / "skills"),
                ("workspace", ws / ".code-agent" / "skills"),
                ("agents", ws / ".agents" / "skills"),
            ]
        )
    return roots


def discover_skills(workspace_root: str | None = None) -> list[dict]:
    found: dict[str, dict] = {}
    for source, root in skill_roots(workspace_root):
        if not root.exists():
            continue
        for skill_md in root.glob("*/SKILL.md"):
            parsed = _parse_skill_md(skill_md)
            if not parsed:
                continue
            parsed["source"] = source
            found[parsed["name"]] = parsed
    return list(found.values())


def list_skill_catalog(workspace_root: str | None = None) -> list[dict]:
    items = []
    for s in discover_skills(workspace_root):
        items.append(
            {
                "name": s["name"],
                "description": s["description"],
                "source": s["source"],
                "path": s["path"],
                "enabled": True,
                "invalid_reason": s.get("invalid_reason"),
            }
        )
    return items


def load_skill_body(workspace_root: str | None, name: str) -> str | None:
    for s in discover_skills(workspace_root):
        if s["name"] == name and not s.get("invalid_reason"):
            return f"# Skill: {name}\n\n{s['description']}\n\n{s['body']}"
    return None
