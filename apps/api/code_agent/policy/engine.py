from __future__ import annotations

import re

from code_agent.config import settings
from code_agent.policy.commands import (
    command_allowed_in_sandbox,
    command_needs_confirm,
    is_command_blocked,
)

_AUTO_RUN_LEVELS = frozenset({"manual", "sandbox", "full"})

# Re-export command helpers for existing imports.
__all__ = [
    "auto_run_level",
    "command_needs_confirm",
    "command_needs_approval",
    "get_auto_run_level",
    "is_command_blocked",
    "is_protected",
    "tool_needs_approval",
]


async def get_auto_run_level() -> str:
    """Resolve policy.auto_run from DB settings, then YAML config."""
    try:
        from code_agent.db.models import Setting

        row = await Setting.get_or_none(key="policy.auto_run")
        if row is not None and row.value_json is not None:
            level = str(row.value_json).strip().lower()
            if level in _AUTO_RUN_LEVELS:
                return level
    except Exception:
        pass
    level = str(settings.get("policy.auto_run") or "sandbox").strip().lower()
    return level if level in _AUTO_RUN_LEVELS else "sandbox"


def auto_run_level() -> str:
    """Sync resolver for tests and non-async callers."""
    level = str(settings.get("policy.auto_run") or "sandbox").strip().lower()
    return level if level in _AUTO_RUN_LEVELS else "sandbox"


def command_needs_approval(command: str, level: str) -> bool:
    """Whether run_command should pause for user approval."""
    text = (command or "").strip()
    if not text or is_command_blocked(text):
        return False
    if level == "manual":
        return True
    if level == "full":
        return False
    # sandbox: whitelist auto-runs; dangerous or unknown commands need approval.
    if command_needs_confirm(text):
        return True
    return not command_allowed_in_sandbox(text)


async def tool_needs_approval(tool: str, *, kind: str, details: dict | None = None) -> bool:
    """Return True when the UI must confirm before executing a tool."""
    details = details or {}
    level = await get_auto_run_level()

    if tool == "run_command":
        return command_needs_approval(str(details.get("command") or ""), level)

    if tool in {"write_file", "search_replace"}:
        path = str(details.get("path") or "")
        if is_protected(path):
            return True
        return level == "manual"

    if tool == "delete_file":
        path = str(details.get("path") or "")
        if is_protected(path):
            return True
        return level in {"manual", "sandbox"}

    if tool.startswith("git_"):
        if level == "manual":
            return True
        if level == "full":
            return tool in {"git_push", "git_reset"}
        return tool in {"git_commit", "git_push", "git_pull", "git_checkout", "git_reset"}

    return level == "manual"


def is_protected(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1]
    globs = settings.get("policy.protected_globs") or []
    for g in globs:
        pat = "^" + re.escape(g).replace("\\*", ".*") + "$"
        if re.match(pat, name, re.IGNORECASE) or re.match(pat, path.replace("\\", "/"), re.IGNORECASE):
            return True
    return False
