from __future__ import annotations

from typing import Any

from code_agent.crypto import decrypt_secret, encrypt_secret, mask_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.capabilities import supports_thinking
from code_agent.llm.codex_gateway import canonicalize_codex_base_url, is_codex_gateway
from code_agent.llm.models_sync import normalize_base_url_for_kind, sync_provider_models
from code_agent.llm.thinking import normalize_thinking_level, thinking_enabled
from code_agent.plugins.base import registry


def _looks_reasoner(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return any(token in name for token in ("reasoner", "thinking")) or name.startswith(
        ("o1", "o3", "o4")
    )


def register_builtin_providers() -> None:
    from code_agent.plugins.builtin_llm import register_builtin_llm_plugins

    register_builtin_llm_plugins()


async def resolve_chat_model(model_pk: str | None, thinking_level: str = "off"):
    level = normalize_thinking_level(thinking_level)
    thinking = thinking_enabled(level)
    chat, row = await get_chat_model(model_pk)
    if not row:
        return chat, row

    caps = row.capabilities_json or {}
    can_think = supports_thinking(caps)
    siblings = await LlmModel.filter(provider_id=row.provider_id, enabled=True)

    def _pair_stem(model_id: str | None) -> str:
        name = (model_id or "").lower()
        for suffix in ("-reasoner", "-thinking", "-think"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def _paired(want_reasoner: bool):
        stem = _pair_stem(row.model_id)
        for sibling in siblings:
            if sibling.id == row.id:
                continue
            if _pair_stem(sibling.model_id) != stem:
                continue
            if _looks_reasoner(sibling.model_id) == want_reasoner:
                return sibling
        return None

    if thinking and can_think and not _looks_reasoner(row.model_id):
        pick = _paired(True)
        if pick:
            chat, row = await get_chat_model(str(pick.id))

    if not thinking and _looks_reasoner(row.model_id):
        pick = _paired(False)
        if pick:
            chat, row = await get_chat_model(str(pick.id))

    if chat is not None:
        from code_agent.llm.adapters import get_llm_adapter

        provider = await row.provider
        adapter = get_llm_adapter(provider)
        chat = adapter.apply_thinking(chat, provider, row, level)
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
    spec = registry.get_provider(provider.kind)
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
    caps = m.capabilities_json or {}
    availability = caps.get("availability") if isinstance(caps, dict) else None
    return {
        "id": str(m.id),
        "provider_id": str(m.provider_id),
        "model_id": m.model_id,
        "display_name": m.display_name,
        "context_window": m.context_window,
        "supports_tools": m.supports_tools,
        "supports_vision": m.supports_vision,
        "capabilities": caps,
        "availability": availability if isinstance(availability, dict) else None,
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
    preset = registry.presets.get(kind)
    if not preset:
        raise ValueError(f"unknown preset: {kind}")
    key = api_key if api_key not in (None, "") else preset.get("default_api_key") or ""
    provider = await LlmProvider.filter(kind=preset["kind"]).first()
    if provider is None and preset["kind"] == "aivalux":
        for row in await LlmProvider.all():
            if is_codex_gateway(row):
                provider = row
                break
    if provider:
        if key:
            provider.api_key_encrypted = encrypt_secret(key)
        provider.base_url = (
            canonicalize_codex_base_url(preset["base_url"])
            if preset["kind"] == "aivalux"
            else normalize_base_url_for_kind(preset["kind"], preset["base_url"])
        )
        provider.name = preset["name"]
        provider.kind = preset["kind"]
        provider.enabled = True
        await provider.save()
    else:
        provider = await LlmProvider.create(
            name=preset["name"],
            kind=preset["kind"],
            base_url=(
                canonicalize_codex_base_url(preset["base_url"])
                if preset["kind"] == "aivalux"
                else normalize_base_url_for_kind(preset["kind"], preset["base_url"])
            ),
            api_key_encrypted=encrypt_secret(key),
            enabled=True,
        )

    if sync_models:
        await sync_provider_models(provider, make_default=make_default)
    return provider


__all__ = [
    "apply_preset",
    "encrypt_secret",
    "get_chat_model",
    "model_public",
    "provider_public",
    "register_builtin_providers",
    "resolve_chat_model",
    "sync_provider_models",
]
