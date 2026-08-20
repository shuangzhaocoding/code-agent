from __future__ import annotations

from typing import Any

from code_agent.crypto import decrypt_secret, encrypt_secret, mask_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.capabilities import merge_runtime_params, supports_thinking
from code_agent.llm.models_sync import normalize_base_url, sync_provider_models
from code_agent.llm.thinking import normalize_thinking_level, thinking_enabled, thinking_extra_body, thinking_off_extra_body
from code_agent.plugins.base import ProviderSpec, registry


def _looks_reasoner(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return any(token in name for token in ("reasoner", "thinking")) or name.startswith(
        ("o1", "o3", "o4")
    )


class CompatChatOpenAI:
    """ChatOpenAI that keeps DeepSeek/OpenRouter `reasoning_content` on stream chunks."""

    @staticmethod
    def wrap():
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import AIMessage, AIMessageChunk

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


_COMPAT_CHAT = None


def _compat_chat_cls():
    global _COMPAT_CHAT
    if _COMPAT_CHAT is None:
        _COMPAT_CHAT = CompatChatOpenAI.wrap()
    return _COMPAT_CHAT


def openai_compat_factory(provider: LlmProvider, model: LlmModel):
    cls = _compat_chat_cls()
    kwargs: dict[str, Any] = {
        "model": model.model_id,
        "api_key": decrypt_secret(provider.api_key_encrypted) or "no-key",
        "base_url": provider.base_url or None,
        "streaming": True,
        "default_headers": provider.extra_headers or None,
    }
    kwargs.update(merge_runtime_params(model.capabilities_json, model.params_json))
    return cls(**kwargs)


PROVIDER_PRESETS: dict[str, dict] = {
    "deepseek": {
        "name": "DeepSeek",
        "kind": "deepseek",
        "title": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
    },
    "ollama": {
        "name": "Ollama",
        "kind": "ollama",
        "title": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_api_key": "ollama",
    },
    "openai": {
        "name": "OpenAI",
        "kind": "openai",
        "title": "OpenAI",
        "base_url": "https://api.openai.com/v1",
    },
    "aivalux": {
        "name": "AIValux",
        "kind": "gateway",
        "title": "AIValux 中转站",
        "base_url": "https://www.aivalux.com/v1",
    },
}


def register_builtin_providers() -> None:
    kinds = [
        ("openai_compat", "OpenAI Compatible"),
        ("openai", "OpenAI"),
        ("deepseek", "DeepSeek"),
        ("ollama", "Ollama"),
        ("gateway", "API Gateway"),
        ("custom", "Custom OpenAI Compatible"),
    ]
    for kind, title in kinds:
        registry.register_provider(
            ProviderSpec(kind=kind, factory=openai_compat_factory, source="builtin", title=title)
        )


async def resolve_chat_model(model_pk: str | None, thinking_level: str = "off"):
    level = normalize_thinking_level(thinking_level)
    thinking = thinking_enabled(level)
    chat, row = await get_chat_model(model_pk)
    if not row:
        return chat, row

    caps = row.capabilities_json or {}
    can_think = supports_thinking(caps)
    siblings = await LlmModel.filter(provider_id=row.provider_id, enabled=True)

    if thinking and can_think and not _looks_reasoner(row.model_id):
        pick = next(
            (
                m
                for m in siblings
                if _looks_reasoner(m.model_id) or supports_thinking(m.capabilities_json)
            ),
            None,
        )
        if pick and pick.id != row.id:
            chat, row = await get_chat_model(str(pick.id))

    if not thinking and _looks_reasoner(row.model_id):
        pick = next((m for m in siblings if not _looks_reasoner(m.model_id)), None)
        if pick:
            chat, row = await get_chat_model(str(pick.id))

    if chat is not None:
        extra = dict(getattr(chat, "extra_body", None) or {})
        if thinking and can_think:
            extra.update(thinking_extra_body(level, row.model_id if row else None))
        else:
            extra.pop("thinking", None)
            extra.update(thinking_off_extra_body(row.model_id if row else None))
        chat = chat.model_copy(update={"extra_body": extra or None})
    return chat, row


async def get_chat_model(model_pk: str | None):
    query = LlmModel.filter(enabled=True)
    if model_pk:
        model = await LlmModel.get_or_none(id=model_pk)
    else:
        model = await query.filter(is_default=True).first()
        if not model:
            model = await query.first()
    if not model:
        return None, None
    provider = await model.provider
    if not provider.enabled:
        return None, None
    spec = registry.providers.get(provider.kind) or registry.providers.get("openai_compat")
    if not spec:
        return None, None
    return spec.factory(provider, model), model


def provider_public(p: LlmProvider) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "kind": p.kind,
        "base_url": p.base_url,
        "api_key_masked": mask_secret(decrypt_secret(p.api_key_encrypted)),
        "has_key": bool(p.api_key_encrypted),
        "extra_headers": p.extra_headers,
        "enabled": p.enabled,
    }


def model_public(m: LlmModel) -> dict:
    return {
        "id": str(m.id),
        "provider_id": str(m.provider_id),
        "model_id": m.model_id,
        "display_name": m.display_name,
        "context_window": m.context_window,
        "supports_tools": m.supports_tools,
        "supports_vision": m.supports_vision,
        "capabilities": m.capabilities_json or {},
        "params": m.params_json or {},
        "is_default": m.is_default,
        "enabled": m.enabled,
    }


async def apply_preset(
    kind: str,
    api_key: str | None = None,
    make_default: bool = True,
    *,
    sync_models: bool = True,
) -> LlmProvider:
    preset = PROVIDER_PRESETS.get(kind)
    if not preset:
        raise ValueError(f"unknown preset: {kind}")
    key = api_key if api_key not in (None, "") else preset.get("default_api_key") or ""
    provider = await LlmProvider.filter(kind=preset["kind"]).first()
    if provider:
        if key:
            provider.api_key_encrypted = encrypt_secret(key)
        provider.base_url = normalize_base_url(preset["base_url"])
        provider.name = preset["name"]
        provider.kind = preset["kind"]
        provider.enabled = True
        await provider.save()
    else:
        provider = await LlmProvider.create(
            name=preset["name"],
            kind=preset["kind"],
            base_url=normalize_base_url(preset["base_url"]),
            api_key_encrypted=encrypt_secret(key),
            enabled=True,
        )

    if sync_models:
        await sync_provider_models(provider, make_default=make_default)
    return provider


__all__ = [
    "PROVIDER_PRESETS",
    "apply_preset",
    "encrypt_secret",
    "get_chat_model",
    "model_public",
    "provider_public",
    "register_builtin_providers",
    "resolve_chat_model",
    "sync_provider_models",
]
