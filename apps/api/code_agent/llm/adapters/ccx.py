from __future__ import annotations

from typing import Any

from code_agent.crypto import decrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.adapters._shared import (
    BASE_CONFIG_SCHEMA,
    compat_chat_cls,
    decrypt_api_key,
    list_models_openai_compat,
    normalize_openai_base_url,
    probe_openai_compat,
)
from code_agent.llm.adapters.openai import _responses_runtime_kwargs, _uses_responses_api
from code_agent.llm.capabilities import merge_runtime_params, rejects_sampling_params, supports_thinking
from code_agent.llm.thinking import (
    THINKING_LEVELS,
    normalize_thinking_level,
    thinking_enabled,
    thinking_extra_body,
    thinking_off_extra_body,
)

PLUGIN_ID = "builtin.llm.ccx"

DEFAULT_BASE_URL = "http://127.0.0.1:3688/v1"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "CCX",
        "kind": "ccx",
        "title": "CCX 网关",
        "base_url": DEFAULT_BASE_URL,
    },
]

KINDS: list[tuple[str, str]] = [("ccx", "CCX")]

_QWEN_BUDGET = {"low": 1024, "medium": 8192, "high": 32768}


def normalize_ccx_base_url(base_url: str) -> str:
    return normalize_openai_base_url(base_url, default=DEFAULT_BASE_URL)


def _ccx_auth_headers(provider: LlmProvider) -> tuple[str, dict[str, str]]:
    base_url = normalize_ccx_base_url(provider.base_url or "")
    api_key = decrypt_secret(provider.api_key_encrypted) or ""
    extra = dict(getattr(provider, "extra_headers", None) or {})
    headers = dict(extra)
    headers.setdefault("User-Agent", "code-agent/1.0")
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    return base_url, headers


def _uses_qwen_thinking(model_id: str | None) -> bool:
    return "qwen" in (model_id or "").lower()


def _qwen_thinking_extra(level: str) -> dict[str, Any]:
    normalized = normalize_thinking_level(level)
    if normalized == "off":
        return {"enable_thinking": False}
    budget = _QWEN_BUDGET.get(normalized, _QWEN_BUDGET["medium"])
    return {"enable_thinking": True, "thinking_budget": budget}


class CcxAdapter:
    kind = "ccx"
    title = "CCX"
    description = (
        "CCX AI API 代理网关（Chat Completions + Responses）。"
        "GPT-5 / o 系列走 /v1/responses + reasoning.effort；"
        "DeepSeek / Qwen 等走 Chat 并按模型名适配 thinking 参数。"
    )
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = THINKING_LEVELS

    def normalize_base_url(self, base_url: str) -> str:
        return normalize_ccx_base_url(base_url)

    def create_chat_model(self, provider: LlmProvider, model: LlmModel):
        cls = compat_chat_cls()
        base_url, headers = _ccx_auth_headers(provider)
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
        base_url, headers = _ccx_auth_headers(provider)
        if base_url != (provider.base_url or "").rstrip("/"):
            provider.base_url = base_url
            await provider.save()
        return await list_models_openai_compat(provider, base_url, headers)

    async def probe_model(self, provider: LlmProvider, model_id: str) -> dict[str, Any]:
        base_url, headers = _ccx_auth_headers(provider)
        return await probe_openai_compat(
            base_url,
            headers,
            model_id,
            use_responses_api=_uses_responses_api(model_id),
        )

    def apply_thinking(self, chat: Any, provider: LlmProvider, model: LlmModel, level: str):
        if _uses_responses_api(model.model_id):
            if not supports_thinking(model.capabilities_json or {}) and not thinking_enabled(level):
                return chat
            updates = _responses_runtime_kwargs(model.model_id, level)
            extra = dict(getattr(chat, "extra_body", None) or {})
            extra.pop("thinking", None)
            extra.pop("enable_thinking", None)
            updates["extra_body"] = extra or None
            return chat.model_copy(update=updates)

        extra = dict(getattr(chat, "extra_body", None) or {})
        caps = model.capabilities_json or {}
        if thinking_enabled(level) and supports_thinking(caps):
            if _uses_qwen_thinking(model.model_id):
                extra.update(_qwen_thinking_extra(level))
                extra.pop("thinking", None)
            else:
                extra.pop("enable_thinking", None)
                extra.update(thinking_extra_body(level, model.model_id))
        else:
            extra.pop("thinking", None)
            if _uses_qwen_thinking(model.model_id):
                extra.update(_qwen_thinking_extra("off"))
            else:
                extra.pop("enable_thinking", None)
                extra.update(thinking_off_extra_body(model.model_id))
        return chat.model_copy(update={"extra_body": extra or None})


ccx_adapter = CcxAdapter()
