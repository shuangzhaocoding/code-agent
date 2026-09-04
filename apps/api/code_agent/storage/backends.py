from __future__ import annotations

import os
from typing import Any

from code_agent.config import settings


def storage_database_backend() -> str:
    raw = os.environ.get("CODE_AGENT_STORAGE_DATABASE") or settings.get("storage.database") or "sqlite"
    token = str(raw).strip().lower()
    return token if token in {"sqlite", "postgres"} else "sqlite"


def storage_events_backend() -> str:
    raw = os.environ.get("CODE_AGENT_STORAGE_EVENTS") or settings.get("storage.events") or "sqlite"
    token = str(raw).strip().lower()
    return token if token in {"sqlite", "redis"} else "sqlite"


def storage_checkpoint_backend() -> str:
    raw = os.environ.get("CODE_AGENT_STORAGE_CHECKPOINT") or settings.get("storage.checkpoint") or "sqlite"
    token = str(raw).strip().lower()
    return token if token in {"sqlite", "postgres"} else "sqlite"


def postgres_url() -> str:
    return (
        os.environ.get("CODE_AGENT_POSTGRES_URL")
        or settings.get("storage.postgres_url")
        or ""
    ).strip()


def redis_url() -> str:
    return (
        os.environ.get("CODE_AGENT_REDIS_URL")
        or settings.get("storage.redis_url")
        or "redis://127.0.0.1:6379/0"
    ).strip()


def checkpoint_postgres_url() -> str:
    return (
        os.environ.get("CODE_AGENT_CHECKPOINT_POSTGRES_URL")
        or settings.get("storage.checkpoint_postgres_url")
        or postgres_url()
    ).strip()


def resolve_database_url() -> str:
    if storage_database_backend() == "postgres":
        url = postgres_url()
        if not url:
            raise RuntimeError("storage.database=postgres requires storage.postgres_url or CODE_AGENT_POSTGRES_URL")
        if url.startswith("postgresql://"):
            url = "postgres://" + url[len("postgresql://") :]
        return url
    return f"sqlite://{settings.data_dir / 'code_agent.sqlite3'}"


def storage_public() -> dict[str, Any]:
    return {
        "database": storage_database_backend(),
        "events": storage_events_backend(),
        "checkpoint": storage_checkpoint_backend(),
        "postgres_configured": bool(postgres_url()),
        "redis_configured": bool(redis_url()),
    }
