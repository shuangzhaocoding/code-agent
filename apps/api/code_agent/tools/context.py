from __future__ import annotations

import contextvars
from typing import Any

_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
_workspace: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("workspace", default=None)


def set_tool_context(run_id: str, workspace: dict[str, Any]) -> None:
    _run_id.set(run_id)
    _workspace.set(workspace)


def get_run_id() -> str:
    value = _run_id.get()
    if not value:
        raise RuntimeError("No active run context")
    return value


def get_workspace() -> dict[str, Any]:
    value = _workspace.get()
    if not value:
        raise RuntimeError("No active workspace context")
    return value
