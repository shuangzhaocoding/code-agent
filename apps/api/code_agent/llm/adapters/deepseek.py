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
from code_agent.llm.thinking import THINKING_LEVELS, normalize_thinking_level, thinking_enabled

PLUGIN_ID = "builtin.llm.deepseek"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "DeepSeek",
        "kind": "deepseek",
        "title": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
    },
]

KINDS: list[tuple[str, str]] = [("deepseek", "DeepSeek")]

_BUDGET = {"low": 1024, "medium": 8192, "high": 32768}


def _thinking_extra_body(level: str, model_id: str | None) -> dict[str, Any]:
    normalized = normalize_thinking_level(level)
    if normalized == "off":
        return {"thinking": {"type": "disabled"}}
    budget = _BUDGET.get(normalized, _BUDGET["medium"])
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


class DeepSeekAdapter:
    kind = "deepseek"
    title = "DeepSeek"
    description = "DeepSeek 官方 API；支持思考强度与视觉模型（如 deepseek-v4-flash-vision-exp）。"
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = THINKING_LEVELS

    def normalize_base_url(self, base_url: str) -> str:
        return normalize_openai_base_url(base_url, default="https://api.deepseek.com/v1")

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
            extra.update(_thinking_extra_body(level, model.model_id))
        else:
            extra.update(_thinking_extra_body("off", model.model_id))
        return chat.model_copy(update={"extra_body": extra or None})


deepseek_adapter = DeepSeekAdapter()
