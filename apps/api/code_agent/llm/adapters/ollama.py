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
from code_agent.llm.capabilities import merge_runtime_params

PLUGIN_ID = "builtin.llm.ollama"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "Ollama",
        "kind": "ollama",
        "title": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_api_key": "ollama",
    },
]

KINDS: list[tuple[str, str]] = [("ollama", "Ollama")]


class OllamaAdapter:
    kind = "ollama"
    title = "Ollama"
    description = "本地 Ollama OpenAI 兼容接口；不支持远程思考强度参数。"
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = ("off",)

    def normalize_base_url(self, base_url: str) -> str:
        return normalize_openai_base_url(base_url, default="http://127.0.0.1:11434/v1")

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
        extra.pop("thinking", None)
        return chat.model_copy(update={"extra_body": extra or None})


ollama_adapter = OllamaAdapter()
