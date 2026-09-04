from __future__ import annotations

import asyncio

from code_agent.config import settings

_slots: asyncio.Semaphore | None = None
_active_runs: set[str] = set()


def max_concurrent_runs() -> int:
    try:
        return max(1, int(settings.get("agent.max_concurrent_runs") or 2))
    except (TypeError, ValueError):
        return 2


def _semaphore() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(max_concurrent_runs())
    return _slots


def reset_run_slots() -> None:
    """Test helper: rebuild semaphore after config changes."""
    global _slots
    _slots = None
    _active_runs.clear()


def active_run_count() -> int:
    return len(_active_runs)


def active_run_ids() -> set[str]:
    return set(_active_runs)


class RunCapacity:
    """Limit concurrent LangGraph runs to protect the shared event loop."""

    async def __aenter__(self) -> None:
        await _semaphore().acquire()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        _semaphore().release()

    @staticmethod
    def mark_started(run_id: str) -> None:
        _active_runs.add(str(run_id))

    @staticmethod
    def mark_finished(run_id: str) -> None:
        _active_runs.discard(str(run_id))
