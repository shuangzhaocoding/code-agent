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
from code_agent.llm.thinking import THINKING_LEVELS, reasoning_effort_for_level, thinking_enabled

PLUGIN_ID = "builtin.llm.openai"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "OpenAI",
        "kind": "openai",
        "title": "OpenAI",
        "base_url": "https://api.openai.com/v1",
    },
]

KINDS: list[tuple[str, str]] = [("openai", "OpenAI")]


def _uses_responses_api(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    if name.startswith(("o1", "o3", "o4")):
        return True
    return name.startswith("gpt-5") and "chat" not in name


def _responses_runtime_kwargs(model_id: str | None, thinking_level: str = "off") -> dict[str, Any]:
    effort = reasoning_effort_for_level(thinking_level, model_id)
    if effort is None:
        effort = "low" if not thinking_enabled(thinking_level) else "medium"
    return {
        "use_responses_api": True,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": effort, "summary": "auto"},
    }


class OpenAIAdapter:
    kind = "openai"
    title = "OpenAI"
    description = "OpenAI 官方 API；o 系列 / GPT-5 通过 Responses API 的 reasoning.effort 控制思考强度。"
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
        }
        if _uses_responses_api(model.model_id):
            kwargs.update(_responses_runtime_kwargs(model.model_id, "off"))
        else:
            kwargs["use_responses_api"] = False
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
        return await probe_openai_compat(
            base_url,
            headers,
            model_id,
            use_responses_api=_uses_responses_api(model_id),
        )

    def apply_thinking(self, chat: Any, provider: LlmProvider, model: LlmModel, level: str):
        if not _uses_responses_api(model.model_id):
            extra = dict(getattr(chat, "extra_body", None) or {})
            extra.pop("thinking", None)
            return chat.model_copy(update={"extra_body": extra or None})

        caps = model.capabilities_json or {}
        if not supports_thinking(caps) and not thinking_enabled(level):
            return chat

        updates = _responses_runtime_kwargs(model.model_id, level)
        extra = dict(getattr(chat, "extra_body", None) or {})
        extra.pop("thinking", None)
        updates["extra_body"] = extra or None
        return chat.model_copy(update=updates)


openai_adapter = OpenAIAdapter()
