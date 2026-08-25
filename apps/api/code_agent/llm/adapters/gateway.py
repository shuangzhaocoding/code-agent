from __future__ import annotations

from typing import Any

from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.adapters._shared import (
    BASE_CONFIG_SCHEMA,
    compat_chat_cls,
    decrypt_api_key,
    list_models_openai_compat,
    probe_openai_compat,
    standard_auth_headers,
)
from code_agent.llm.capabilities import merge_runtime_params, rejects_sampling_params, supports_thinking
from code_agent.llm.codex_gateway import (
    canonicalize_codex_base_url,
    chat_runtime_kwargs,
    is_codex_gateway,
    request_headers as codex_request_headers,
)
from code_agent.llm.thinking import THINKING_LEVELS, thinking_enabled, thinking_extra_body, thinking_off_extra_body
from code_agent.crypto import decrypt_secret

PLUGIN_ID = "builtin.llm.gateway"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "AIValux Codex",
        "kind": "aivalux",
        "title": "AIValux Codex 中转",
        "base_url": "https://www.aivalux.com/v1",
    },
    {
        "name": "API Gateway",
        "kind": "gateway",
        "title": "OpenAI 兼容中转",
        "base_url": "https://api.example.com/v1",
    },
]

KINDS: list[tuple[str, str]] = [
    ("aivalux", "AIValux Codex"),
    ("gateway", "API Gateway"),
]


def _auth_headers(provider: LlmProvider) -> tuple[str, dict[str, str]]:
    api_key = decrypt_secret(provider.api_key_encrypted) or ""
    extra = dict(getattr(provider, "extra_headers", None) or {})
    if is_codex_gateway(provider):
        headers = codex_request_headers(extra)
        base_url = canonicalize_codex_base_url(provider.base_url or "")
    else:
        headers = dict(extra)
        headers.setdefault("User-Agent", "code-agent/1.0")
        from code_agent.llm.adapters._shared import normalize_openai_base_url

        base_url = normalize_openai_base_url(provider.base_url or "")
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    return base_url, headers


class GatewayAdapter:
    kind = "gateway"
    title = "API Gateway"
    description = (
        "OpenAI 兼容中转站。Codex 中继（AIValux）使用 Responses API + reasoning.effort；"
        "通用中转按模型名决定是否发送 DeepSeek 风格 thinking 参数。"
    )
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = THINKING_LEVELS

    def normalize_base_url(self, base_url: str) -> str:
        if "aivalux.com" in (base_url or "").lower():
            return canonicalize_codex_base_url(base_url)
        from code_agent.llm.adapters._shared import normalize_openai_base_url

        return normalize_openai_base_url(base_url)

    def create_chat_model(self, provider: LlmProvider, model: LlmModel):
        cls = compat_chat_cls()
        base_url, headers = _auth_headers(provider)
        kwargs: dict[str, Any] = {
            "model": model.model_id,
            "api_key": decrypt_api_key(provider),
            "base_url": base_url,
            "default_headers": headers,
        }
        if is_codex_gateway(provider):
            kwargs.update(chat_runtime_kwargs(model.model_id, "off"))
        else:
            kwargs["use_responses_api"] = False
        kwargs.update(merge_runtime_params(model.capabilities_json, model.params_json))
        if rejects_sampling_params(model.model_id) or is_codex_gateway(provider):
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        return cls(**kwargs)

    async def list_models(self, provider: LlmProvider) -> list[dict[str, Any]]:
        base_url, headers = _auth_headers(provider)
        if base_url != (provider.base_url or "").rstrip("/"):
            provider.base_url = base_url
            if is_codex_gateway(provider) and provider.kind != "aivalux":
                provider.kind = "aivalux"
            await provider.save()
        return await list_models_openai_compat(provider, base_url, headers)

    async def probe_model(self, provider: LlmProvider, model_id: str) -> dict[str, Any]:
        base_url, headers = _auth_headers(provider)
        return await probe_openai_compat(
            base_url,
            headers,
            model_id,
            use_responses_api=is_codex_gateway(provider),
        )

    def apply_thinking(self, chat: Any, provider: LlmProvider, model: LlmModel, level: str):
        extra = dict(getattr(chat, "extra_body", None) or {})
        if is_codex_gateway(provider):
            extra.pop("thinking", None)
            updates = {"extra_body": extra or None, **chat_runtime_kwargs(model.model_id, level)}
            return chat.model_copy(update=updates)

        caps = model.capabilities_json or {}
        if thinking_enabled(level) and supports_thinking(caps):
            extra.update(thinking_extra_body(level, model.model_id))
        else:
            extra.pop("thinking", None)
            extra.update(thinking_off_extra_body(model.model_id))
        return chat.model_copy(update={"extra_body": extra or None})


gateway_adapter = GatewayAdapter()
