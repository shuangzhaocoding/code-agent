from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from code_agent.crypto import decrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.codex_gateway import (
    canonicalize_codex_base_url,
    is_codex_gateway,
    request_headers as codex_request_headers,
)
from code_agent.llm.models_sync import normalize_base_url

PROBE_PROMPT = "Reply with exactly pong"
PROBE_TIMEOUT = 18.0
PROBE_CONCURRENCY = 4


def _error_text(res: httpx.Response) -> str:
    try:
        payload = res.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)[:240]
            return str(payload.get("message") or payload.get("detail") or payload)[:240]
    except Exception:
        pass
    return (res.text or f"HTTP {res.status_code}")[:240]


async def _probe_one(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    model_id: str,
    responses: bool,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    if responses:
        url = f"{base_url}/responses"
        body: dict[str, Any] = {
            "model": model_id,
            "input": PROBE_PROMPT,
            "store": False,
            "max_output_tokens": 16,
        }
    else:
        url = f"{base_url}/chat/completions"
        body = {
            "model": model_id,
            "messages": [{"role": "user", "content": PROBE_PROMPT}],
            "max_tokens": 16,
        }
    try:
        res = await client.post(url, headers=headers, json=body)
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        if res.status_code >= 400:
            return {"ok": False, "error": _error_text(res), "latency_ms": latency, "status": res.status_code}
        return {"ok": True, "error": "", "latency_ms": latency, "status": res.status_code}
    except httpx.TimeoutException:
        return {"ok": False, "error": "请求超时", "latency_ms": int(PROBE_TIMEOUT * 1000), "status": 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "latency_ms": 0, "status": 0}


async def iter_probe_provider_models(provider: LlmProvider):
    """Yield progress events while pinging each stored model."""
    models = await LlmModel.filter(provider_id=provider.id, enabled=True)
    if not models:
        models = await LlmModel.filter(provider_id=provider.id)
    total = len(models)
    yield {"type": "start", "total": total}
    if not models:
        yield {"type": "done", "ok_count": 0, "fail_count": 0, "total": 0}
        return

    api_key = decrypt_secret(provider.api_key_encrypted) or ""
    responses = is_codex_gateway(provider)
    if responses:
        base_url = canonicalize_codex_base_url(provider.base_url or "")
        headers = codex_request_headers(provider.extra_headers)
    else:
        base_url = normalize_base_url(provider.base_url or "")
        headers = dict(provider.extra_headers or {})
        headers.setdefault("User-Agent", "code-agent/1.0")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers["Content-Type"] = "application/json"

    sem = asyncio.Semaphore(PROBE_CONCURRENCY)
    checked_at = datetime.now(timezone.utc).isoformat()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def run(row: LlmModel) -> None:
        async with sem:
            result = await _probe_one(
                client,
                base_url=base_url,
                headers=headers,
                model_id=row.model_id,
                responses=responses,
            )
        caps = dict(row.capabilities_json or {})
        caps["availability"] = {
            "ok": result["ok"],
            "error": result["error"],
            "checked_at": checked_at,
            "latency_ms": result["latency_ms"],
        }
        row.capabilities_json = caps
        await row.save(update_fields=["capabilities_json"])
        await queue.put(
            {
                "id": str(row.id),
                "model_id": row.model_id,
                "display_name": row.display_name,
                "enabled": row.enabled,
                **result,
                "checked_at": checked_at,
            }
        )

    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
        tasks = [asyncio.create_task(run(row)) for row in models]
        done = 0
        ok_count = 0
        fail_count = 0
        try:
            while done < total:
                item = await queue.get()
                done += 1
                if item.get("ok"):
                    ok_count += 1
                else:
                    fail_count += 1
                yield {
                    "type": "item",
                    "done": done,
                    "total": total,
                    "ok_count": ok_count,
                    "fail_count": fail_count,
                    **item,
                }
            await asyncio.gather(*tasks)
        except Exception:
            for task in tasks:
                task.cancel()
            raise
    yield {"type": "done", "ok_count": ok_count, "fail_count": fail_count, "total": total}


async def probe_provider_models(provider: LlmProvider) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async for event in iter_probe_provider_models(provider):
        if event.get("type") == "item":
            items.append(event)
    return items
