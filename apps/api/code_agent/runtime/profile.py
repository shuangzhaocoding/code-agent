from __future__ import annotations

import os
from typing import Any

from code_agent.config import settings


def runtime_profile() -> str:
    raw = os.environ.get("CODE_AGENT_RUNTIME_PROFILE") or settings.get("runtime.profile") or "split"
    token = str(raw).strip().lower()
    return token if token in {"monolith", "split"} else "split"


def agent_worker_mode() -> str:
    """inline | external | auto"""
    raw = os.environ.get("CODE_AGENT_AGENT_WORKER") or settings.get("runtime.agent_worker.mode") or "auto"
    token = str(raw).strip().lower()
    if token in {"inline", "external"}:
        return token
    return "external" if runtime_profile() == "split" else "inline"


def agent_execution_external() -> bool:
    return agent_worker_mode() == "external"


def service_mode(name: str) -> str:
    """inline | standalone"""
    raw = settings.get(f"runtime.{name}.mode") or "inline"
    token = str(raw).strip().lower()
    if runtime_profile() == "monolith":
        return "inline"
    return token if token in {"inline", "standalone"} else "inline"


def service_endpoint(name: str) -> dict[str, Any]:
    host = str(settings.get(f"runtime.{name}.host") or settings.get("server.host") or "127.0.0.1")
    port = int(settings.get(f"runtime.{name}.port") or _default_port(name))
    return {"host": host, "port": port, "url": f"http://{host}:{port}"}


def _default_port(name: str) -> int:
    base = int(settings.get("server.port") or 4060)
    return {
        "terminal": base + 2,
        "preview": base + 3,
        "agent_worker": base + 4,
    }.get(name, base)


def runtime_public() -> dict[str, Any]:
    return {
        "profile": runtime_profile(),
        "agent_worker": {
            "mode": agent_worker_mode(),
            "external": agent_execution_external(),
            **service_endpoint("agent_worker"),
        },
        "terminal": {
            "mode": service_mode("terminal"),
            **service_endpoint("terminal"),
        },
        "preview": {
            "mode": service_mode("preview"),
            **service_endpoint("preview"),
        },
    }
