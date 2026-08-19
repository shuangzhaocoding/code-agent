from __future__ import annotations

import asyncio
import logging
from collections import deque

from fastapi import WebSocket

_MAX_BYTES = 512_000
_buffer: deque[bytes] = deque()


class SystemLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            chunk = (msg + "\n").encode("utf-8", errors="replace")
        except Exception:
            return
        _buffer.append(chunk)
        total = sum(len(item) for item in _buffer)
        while _buffer and total > _MAX_BYTES:
            total -= len(_buffer.popleft())
        asyncio.get_event_loop().create_task(_broadcast(chunk))


_subscribers: set[WebSocket] = set()


async def _broadcast(chunk: bytes) -> None:
    dead: list[WebSocket] = []
    for ws in list(_subscribers):
        try:
            await ws.send_bytes(chunk)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _subscribers.discard(ws)


def snapshot() -> bytes:
    return b"".join(_buffer)


async def subscribe(ws: WebSocket) -> None:
    _subscribers.add(ws)
    if _buffer:
        await ws.send_bytes(snapshot())


def unsubscribe(ws: WebSocket) -> None:
    _subscribers.discard(ws)


def install() -> None:
    handler = SystemLogHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.propagate = True
