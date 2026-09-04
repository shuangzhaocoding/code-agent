from __future__ import annotations

import asyncio
import logging

from code_agent.runtime.run_queue import wait_for_run_slot
from code_agent.services.bootstrap import bootstrap
from code_agent.streaming.run_capacity import RunCapacity, max_concurrent_runs
from code_agent.streaming.run_manager import _execute

logger = logging.getLogger(__name__)


async def _worker_loop(stop: asyncio.Event) -> None:
    tasks: set[asyncio.Task] = set()
    sem = asyncio.Semaphore(max_concurrent_runs())

    async def _run_one(run_id: str) -> None:
        async with sem:
            await _execute(run_id)

    while not stop.is_set():
        try:
            run = await wait_for_run_slot(poll_sec=0.5)
        except asyncio.CancelledError:
            break
        if run is None:
            continue
        task = asyncio.create_task(_run_one(str(run.id)))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_worker() -> None:
    stop = asyncio.Event()
    async with bootstrap(with_checkpointer=True):
        logger.info("Agent worker started (max_concurrent=%s)", max_concurrent_runs())
        try:
            await _worker_loop(stop)
        except KeyboardInterrupt:
            stop.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())

if __name__ == "__main__":
    main()
