from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from code_agent.crypto import decrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.capabilities import default_params, resolve_capabilities
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


def normalize_base_url_for_kind(kind: str, base_url: str) -> str:
    from code_agent.plugins.base import registry

    spec = registry.providers.get(kind)
    adapter = getattr(spec, "adapter", None) if spec else None
    if adapter is not None and hasattr(adapter, "normalize_base_url"):
        return adapter.normalize_base_url(base_url)
    return normalize_base_url(base_url)


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
    """Fetch model list through the provider's LLM adapter plugin."""
    from code_agent.llm.adapters import get_llm_adapter

    adapter = get_llm_adapter(provider)
    return await adapter.list_models(provider)


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
        row = existing.get(model_id)
        previous = row.capabilities_json if row and isinstance(row.capabilities_json, dict) else {}
        caps = resolve_capabilities(model_id, item.get("remote"), item.get("capabilities"), previous)
        chat_ok = is_codex_chat_model(model_id) if is_codex_gateway(provider) else True
        is_default = False
        if is_codex_gateway(provider) and not has_default:
            is_default = model_id == preferred
        elif make_default and index == 0 and not has_default:
            is_default = True
        context_window = int(item.get("context_window") or caps.get("context_window") or 128000)

        if row:
            row.display_name = item["display_name"]
            row.capabilities_json = caps
            row.supports_tools = bool(caps.get("tools", {}).get("supported"))
            row.supports_vision = bool(caps.get("vision", {}).get("supported"))
            row.context_window = context_window
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
                context_window=context_window,
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
