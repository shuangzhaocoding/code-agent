from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid4().hex


class StreamEnvelope(BaseModel):
    v: int = 1
    event_id: str
    run_id: str
    ts: str
    type: str
    seq: int
    payload: dict[str, Any] = Field(default_factory=dict)


BLOCK_TYPES = [
    "user.text",
    "user.references",
    "assistant.markdown",
    "assistant.thinking",
    "assistant.plan",
    "tool.call",
    "tool.result",
    "file.read",
    "file.diff",
    "file.write",
    "file.delete",
    "terminal",
    "todo",
    "skill.activated",
    "approval",
    "error",
    "usage",
]
