from __future__ import annotations

import re

from code_agent.config import settings

_DEFAULT_API_PORT = 4060
_DEFAULT_DEV_UI_PORT = 4061


def protected_ports() -> set[int]:
    """Ports that must not be killed via UI, API, or agent run_command."""
    ports: set[int] = set()
    for key, fallback in (("server.port", _DEFAULT_API_PORT), ("server.dev_ui_port", _DEFAULT_DEV_UI_PORT)):
        try:
            val = int(settings.get(key) or fallback)
            if 1 <= val <= 65535:
                ports.add(val)
        except (TypeError, ValueError):
            ports.add(fallback)
    extra = settings.get("ports.protected") or []
    if isinstance(extra, int):
        extra = [extra]
    for item in extra:
        try:
            val = int(item)
            if 1 <= val <= 65535:
                ports.add(val)
        except (TypeError, ValueError):
            continue
    return ports


def command_targets_protected_port(command: str) -> int | None:
    """Return matched protected port if command likely kills/listens on one."""
    text = command.strip().lower()
    if not text:
        return None
    killers = (
        "kill ",
        "kill -",
        "pkill ",
        "killall ",
        "fuser ",
        "kill-port",
        "lsof -",
    )
    if not any(token in text for token in killers):
        return None
    for port in sorted(protected_ports(), reverse=True):
        p = str(port)
        patterns = (
            rf":{re.escape(p)}\b",
            rf"\b{re.escape(p)}/tcp\b",
            rf"\b-i\s*:?{re.escape(p)}\b",
            rf"\bport\s+{re.escape(p)}\b",
            rf"\b{re.escape(p)}\s*$",
            rf"\s{re.escape(p)}\s",
        )
        if any(re.search(pat, text) for pat in patterns):
            return port
    return None
