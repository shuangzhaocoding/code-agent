from __future__ import annotations

import re

from code_agent.config import settings


def is_command_blocked(command: str) -> bool:
    text = command.strip().lower()
    for item in settings.get("policy.command_blacklist") or []:
        if item.lower() in text:
            return True
    from code_agent.ports.protected import command_targets_protected_port

    if command_targets_protected_port(command) is not None:
        return True
    return False


_DANGEROUS_COMMAND = re.compile(
    r"(?:^|[\s;&|])("
    r"rm\s|sudo\s|chmod\s|chown\s|mkfs|shutdown|reboot|"
    r"git\s+(push|reset|clean|rebase)|"
    r"git\s+checkout\s+-f|"
    r"--force\b|curl\s+[^\n]*\|\s*(?:ba)?sh|"
    r":\(\)\s*\{"
    r")",
    re.IGNORECASE,
)


def command_needs_confirm(command: str) -> bool:
    text = command.strip()
    if not text:
        return False
    if is_command_blocked(text):
        return False
    return bool(_DANGEROUS_COMMAND.search(text))


def is_protected(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1]
    globs = settings.get("policy.protected_globs") or []
    for g in globs:
        pat = "^" + re.escape(g).replace("\\*", ".*") + "$"
        if re.match(pat, name, re.IGNORECASE) or re.match(pat, path.replace("\\", "/"), re.IGNORECASE):
            return True
    return False
