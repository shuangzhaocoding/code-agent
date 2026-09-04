from __future__ import annotations

import asyncio

import pytest

from code_agent.config import settings
from code_agent.streaming import run_capacity


@pytest.fixture(autouse=True)
def _reset_slots():
    run_capacity.reset_run_slots()
    settings._cfg.setdefault("agent", {})["max_concurrent_runs"] = 2
    yield
    run_capacity.reset_run_slots()


@pytest.mark.asyncio
async def test_run_capacity_limits_parallelism():
    settings._cfg["agent"]["max_concurrent_runs"] = 1
    run_capacity.reset_run_slots()
    order: list[str] = []

    async def worker(name: str) -> None:
        async with run_capacity.RunCapacity():
            run_capacity.RunCapacity.mark_started(name)
            order.append(f"start:{name}")
            await asyncio.sleep(0.05)
            run_capacity.RunCapacity.mark_finished(name)
            order.append(f"end:{name}")

    await asyncio.gather(worker("a"), worker("b"))
    assert order.index("end:a") < order.index("start:b") or order.index("end:b") < order.index("start:a")


def test_max_concurrent_runs_default():
    assert run_capacity.max_concurrent_runs() == 2
