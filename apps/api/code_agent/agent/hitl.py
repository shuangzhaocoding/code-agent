"""HITL bridge: LangGraph ``interrupt`` + ``Command(resume=...)``.

Tools call ``request_approval()`` → ``interrupt()``. The stream adapter detects
pending interrupts, publishes approval SSE cards, waits for
``POST /api/runs/{id}/approvals/{aid}``, then continues with ``Command(resume=...)``.
"""

from __future__ import annotations

from code_agent.tools.approval import (
    deny_run_approvals,
    request_approval,
    resolve_approval,
    wait_for_approval_resume,
)

__all__ = [
    "deny_run_approvals",
    "request_approval",
    "resolve_approval",
    "wait_for_approval_resume",
]
