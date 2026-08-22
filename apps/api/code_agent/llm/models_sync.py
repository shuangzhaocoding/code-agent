from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from code_agent.crypto import decrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.capabilities import default_params, infer_capabilities
from code_agent.llm.codex_gateway import (
    canonicalize_codex_base_url,
    is_codex_chat_model,
    is_codex_gateway,
    preferred_model_id,
    request_headers as codex_request_headers,
)


def normalize_base_url(base_url: str) -> str:
    """Ensure OpenAI-compatible base URLs end with /v1."""
    raw = (base_url or "").strip()
    if not raw:
        return "https://api.openai.com/v1"
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunparse(parsed._replace(path=path)).rstrip("/")


def _models_url(base_url: str) -> str:
    base = normalize_base_url(base_url)
    return f"{base}/models"


def _format_http_error(res: httpx.Response) -> str:
    try:
        payload = res.json()
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or payload.get("detail")
            code = payload.get("code")
            if message and code:
                return f"{code}: {message}"
            if message:
                return str(message)
    except Exception:
        pass
    if res.status_code in {401, 403}:
        return (
            f"HTTP {res.status_code} — 请检查 API Key 是否正确，"
            f"Base URL 应为 OpenAI 兼容地址（如 https://www.aivalux.com/v1）"
        )
    return f"HTTP {res.status_code} for {res.request.url}"


async def fetch_remote_models(provider: LlmProvider) -> list[dict[str, Any]]:
    """Fetch model list from an OpenAI-compatible /v1/models endpoint."""
    api_key = decrypt_secret(provider.api_key_encrypted) or ""
    if is_codex_gateway(provider):
        headers = codex_request_headers(provider.extra_headers)
        normalized = canonicalize_codex_base_url(provider.base_url or "")
    else:
        headers = dict(provider.extra_headers or {})
        normalized = normalize_base_url(provider.base_url)
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"

    if normalized != (provider.base_url or "").rstrip("/"):
        provider.base_url = normalized
        if is_codex_gateway(provider) and provider.kind != "aivalux":
            provider.kind = "aivalux"
        await provider.save()

    url = _models_url(normalized)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        res = await client.get(url, headers=headers or None)
        if res.status_code >= 400:
            raise ValueError(_format_http_error(res))
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


async def sync_provider_models(
    provider: LlmProvider,
    *,
    make_default: bool = False,
    disable_missing: bool = True,
) -> list[LlmModel]:
    """Fetch remote models and upsert into the database."""
    remote_models = await fetch_remote_models(provider)
    if not remote_models:
        raise ValueError("No models returned from provider")

    existing = {m.model_id: m for m in await LlmModel.filter(provider_id=provider.id)}
    remote_ids = {item["model_id"] for item in remote_models}
    has_default = any(m.is_default for m in existing.values())
    preferred = preferred_model_id([item["model_id"] for item in remote_models]) if is_codex_gateway(provider) else None

    if make_default and not has_default:
        await LlmModel.all().update(is_default=False)

    saved: list[LlmModel] = []
    for index, item in enumerate(remote_models):
        model_id = item["model_id"]
        caps = infer_capabilities(model_id, item.get("remote"))
        row = existing.get(model_id)
        chat_ok = is_codex_chat_model(model_id) if is_codex_gateway(provider) else True
        is_default = False
        if is_codex_gateway(provider) and not has_default:
            is_default = model_id == preferred
        elif make_default and index == 0 and not has_default:
            is_default = True

        if row:
            row.display_name = item["display_name"]
            row.capabilities_json = caps
            row.supports_tools = bool(caps.get("tools", {}).get("supported"))
            row.supports_vision = bool(caps.get("vision", {}).get("supported"))
            row.enabled = chat_ok
            if is_default:
                row.is_default = True
            if not row.params_json:
                row.params_json = default_params(caps)
            await row.save()
        else:
            row = await LlmModel.create(
                provider_id=provider.id,
                model_id=model_id,
                display_name=item["display_name"],
                context_window=128000,
                supports_tools=bool(caps.get("tools", {}).get("supported")),
                supports_vision=bool(caps.get("vision", {}).get("supported")),
                capabilities_json=caps,
                params_json=default_params(caps),
                is_default=is_default,
                enabled=chat_ok,
            )
        saved.append(row)

    if disable_missing:
        for model_id, row in existing.items():
            if model_id not in remote_ids and row.enabled:
                row.enabled = False
                await row.save()

    return saved
