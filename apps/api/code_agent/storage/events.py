from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from code_agent.storage.backends import redis_url, storage_events_backend

logger = logging.getLogger(__name__)

_redis = None


async def _redis_client():
    global _redis
    if _redis is not None:
        return _redis
    try:
        from redis import asyncio as aioredis
    except ImportError as exc:
        raise RuntimeError("storage.events=redis requires `pip install redis`") from exc
    _redis = aioredis.from_url(redis_url(), decode_responses=True)
    return _redis


def events_use_redis() -> bool:
    return storage_events_backend() == "redis"


def _channel(run_id: str) -> str:
    return f"code-agent:run:{run_id}"


async def publish_run_event(run_id: str, envelope: dict[str, Any]) -> None:
    if not events_use_redis():
        return
    try:
        client = await _redis_client()
        await client.publish(_channel(run_id), json.dumps(envelope, ensure_ascii=False))
    except Exception as exc:
        logger.warning("redis publish failed for run %s: %s", run_id, exc)


async def subscribe_run_events(run_id: str) -> AsyncIterator[dict[str, Any]]:
    if not events_use_redis():
        return
        yield  # pragma: no cover — makes this an async generator when unused
    client = await _redis_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(_channel(run_id))
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message or message.get("type") != "message":
                await asyncio.sleep(0.05)
                continue
            data = message.get("data")
            if not data:
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue
    finally:
        await pubsub.unsubscribe(_channel(run_id))
        await pubsub.aclose()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
