from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from code_agent.db.models import Run

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


async def claim_next_run() -> Run | None:
    """Atomically claim the oldest queued run (external worker)."""
    candidate = await Run.filter(status="queued").order_by("started_at").first()
    if candidate is None:
        return None
    updated = await Run.filter(id=candidate.id, status="queued").update(
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    if not updated:
        return None
    return await Run.get(id=candidate.id)


async def wait_for_run_slot(poll_sec: float = 0.4) -> Run | None:
    while True:
        run = await claim_next_run()
        if run is not None:
            return run
        await asyncio.sleep(poll_sec)
