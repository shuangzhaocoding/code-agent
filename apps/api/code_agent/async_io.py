from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_sync(fn: Callable[..., T], *args, **kwargs) -> T:
    """Run blocking I/O in the default thread pool."""
    return await asyncio.to_thread(fn, *args, **kwargs)
