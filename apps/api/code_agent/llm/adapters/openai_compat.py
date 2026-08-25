from __future__ import annotations

from typing import Any

from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.adapters._shared import (
    BASE_CONFIG_SCHEMA,
    compat_chat_cls,
    decrypt_api_key,
    list_models_openai_compat,
    normalize_openai_base_url,
    probe_openai_compat,
    standard_auth_headers,
)
from code_agent.llm.capabilities import merge_runtime_params, rejects_sampling_params, supports_thinking
from code_agent.llm.thinking import THINKING_LEVELS, thinking_enabled, thinking_extra_body, thinking_off_extra_body

PLUGIN_ID = "builtin.llm.openai_compat"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = []

KINDS: list[tuple[str, str]] = [
    ("openai_compat", "OpenAI Compatible"),
    ("custom", "Custom OpenAI Compatible"),
]


class OpenAICompatAdapter:
    """Generic OpenAI Chat Completions compatible adapter for unknown vendors."""

    kind = "openai_compat"
    title = "OpenAI Compatible"
    description = "通用 OpenAI 兼容接口；按模型名推断是否发送 thinking 参数（避免 GPT 网关 502）。"
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = THINKING_LEVELS

    def normalize_base_url(self, base_url: str) -> str:
        return normalize_openai_base_url(base_url)

    def create_chat_model(self, provider: LlmProvider, model: LlmModel):
        cls = compat_chat_cls()
        base_url, headers = standard_auth_headers(provider)
        kwargs: dict[str, Any] = {
            "model": model.model_id,
            "api_key": decrypt_api_key(provider),
            "base_url": base_url,
            "default_headers": headers,
            "use_responses_api": False,
        }
        kwargs.update(merge_runtime_params(model.capabilities_json, model.params_json))
        if rejects_sampling_params(model.model_id):
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        return cls(**kwargs)

    async def list_models(self, provider: LlmProvider) -> list[dict[str, Any]]:
        base_url, headers = standard_auth_headers(provider)
        if base_url != (provider.base_url or "").rstrip("/"):
            provider.base_url = base_url
            await provider.save()
        return await list_models_openai_compat(provider, base_url, headers)

    async def probe_model(self, provider: LlmProvider, model_id: str) -> dict[str, Any]:
        base_url, headers = standard_auth_headers(provider)
        return await probe_openai_compat(base_url, headers, model_id)

    def apply_thinking(self, chat: Any, provider: LlmProvider, model: LlmModel, level: str):
        extra = dict(getattr(chat, "extra_body", None) or {})
        caps = model.capabilities_json or {}
        if thinking_enabled(level) and supports_thinking(caps):
            extra.update(thinking_extra_body(level, model.model_id))
        else:
            extra.pop("thinking", None)
            extra.update(thinking_off_extra_body(model.model_id))
        return chat.model_copy(update={"extra_body": extra or None})


openai_compat_adapter = OpenAICompatAdapter()
