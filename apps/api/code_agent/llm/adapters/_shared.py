from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from code_agent.crypto import decrypt_secret
from code_agent.db.models import LlmModel, LlmProvider

PROBE_PROMPT = "Reply with exactly pong"
PROBE_TIMEOUT = 18.0

_COMPAT_CHAT = None


class CompatChatOpenAI:
    """ChatOpenAI that keeps DeepSeek/OpenRouter `reasoning_content` on stream chunks."""

    @staticmethod
    def wrap():
        from langchain_core.messages import AIMessage, AIMessageChunk
        from langchain_openai import ChatOpenAI

        class _Compat(ChatOpenAI):
            def _convert_chunk_to_generation_chunk(
                self,
                chunk: dict,
                default_chunk_class: type,
                base_generation_info: dict | None,
            ):
                gen = super()._convert_chunk_to_generation_chunk(
                    chunk, default_chunk_class, base_generation_info
                )
                if gen is None:
                    return None
                raw = chunk if isinstance(chunk, dict) else {}
                choices = raw.get("choices") or (raw.get("chunk") or {}).get("choices") or []
                if not choices:
                    return gen
                delta = choices[0].get("delta") or choices[0].get("message") or {}
                reasoning = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or (choices[0].get("message") or {}).get("reasoning_content")
                )
                if reasoning and isinstance(gen.message, (AIMessageChunk, AIMessage)):
                    extra = dict(gen.message.additional_kwargs or {})
                    extra["reasoning_content"] = reasoning
                    gen.message.additional_kwargs = extra
                return gen

        return _Compat


def compat_chat_cls():
    global _COMPAT_CHAT
    if _COMPAT_CHAT is None:
        _COMPAT_CHAT = CompatChatOpenAI.wrap()
    return _COMPAT_CHAT


def normalize_openai_base_url(base_url: str, *, default: str = "https://api.openai.com/v1") -> str:
    raw = (base_url or "").strip()
    if not raw:
        return default
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunparse(parsed._replace(path=path)).rstrip("/")


def error_text(res: httpx.Response) -> str:
    try:
        payload = res.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)[:240]
            message = payload.get("message") or payload.get("error") or payload.get("detail")
            code = payload.get("code")
            if message and code:
                return f"{code}: {message}"[:240]
            if message:
                return str(message)[:240]
    except Exception:
        pass
    if res.status_code in {401, 403}:
        return (
            f"HTTP {res.status_code} — 请检查 API Key 是否正确，"
            f"Base URL 应为 OpenAI 兼容地址（如 https://www.aivalux.com/v1）"
        )
    return (res.text or f"HTTP {res.status_code}")[:240]


def standard_auth_headers(provider: LlmProvider) -> tuple[str, dict[str, str]]:
    api_key = decrypt_secret(provider.api_key_encrypted) or ""
    extra = dict(getattr(provider, "extra_headers", None) or {})
    headers = dict(extra)
    headers.setdefault("User-Agent", "code-agent/1.0")
    base_url = normalize_openai_base_url(provider.base_url or "")
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    return base_url, headers


def decrypt_api_key(provider: LlmProvider) -> str:
    return decrypt_secret(provider.api_key_encrypted) or "no-key"


async def list_models_openai_compat(provider: LlmProvider, base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{base_url}/models"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers or None)
    except httpx.ConnectError as exc:
        raise ValueError(
            f"无法连接 {url} — 请确认服务已启动、端口正确（CCX 常见端口 3688），"
            f"且 Code Agent API 能访问该地址"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(f"请求 {url} 失败: {exc}") from exc
    if res.status_code >= 400:
        raise ValueError(error_text(res))
    payload = res.json()
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Invalid models response: missing data array")
    models: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if not model_id:
            continue
        models.append(
            {
                "model_id": str(model_id),
                "display_name": str(item.get("display_name") or model_id),
                "remote": item,
            }
        )
    return models


async def probe_openai_compat(
    base_url: str,
    headers: dict[str, str],
    model_id: str,
    *,
    use_responses_api: bool = False,
) -> dict[str, Any]:
    headers = dict(headers)
    headers["Content-Type"] = "application/json"
    started = datetime.now(timezone.utc)
    if use_responses_api:
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
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            res = await client.post(url, headers=headers, json=body)
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        if res.status_code >= 400:
            return {"ok": False, "error": error_text(res), "latency_ms": latency, "status": res.status_code}
        return {"ok": True, "error": "", "latency_ms": latency, "status": res.status_code}
    except httpx.TimeoutException:
        return {"ok": False, "error": "请求超时", "latency_ms": int(PROBE_TIMEOUT * 1000), "status": 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "latency_ms": 0, "status": 0}


BASE_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "title": "名称"},
        "kind": {"type": "string", "title": "适配器类型"},
        "base_url": {"type": "string", "title": "Base URL"},
        "api_key": {"type": "string", "title": "API Key", "format": "password"},
        "extra_headers": {"type": "object", "title": "额外请求头"},
    },
    "required": ["name", "base_url"],
}
