from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from code_agent.crypto import encrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.hub import apply_preset, get_chat_model, model_public, provider_public
from code_agent.llm.models_sync import fetch_remote_models, normalize_base_url_for_kind, sync_provider_models
from code_agent.llm.probe import iter_probe_provider_models, probe_provider_models
from code_agent.llm.provider_access import require_provider_available, require_provider_kind
from code_agent.plugins.base import registry

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ProviderIn(BaseModel):
    name: str
    kind: str = "openai_compat"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    extra_headers: dict = Field(default_factory=dict)
    enabled: bool = True
    sync_models: bool = True
    make_default: bool = False


class ModelIn(BaseModel):
    provider_id: str
    model_id: str
    display_name: str | None = None
    context_window: int = 128000
    supports_tools: bool = True
    supports_vision: bool = False
    is_default: bool = False
    params: dict = Field(default_factory=dict)


class SyncModelsIn(BaseModel):
    make_default: bool = False
    disable_missing: bool = True


@router.get("/kinds")
async def kinds():
    return [
        {
            "kind": spec.kind,
            "title": spec.title,
            "source": spec.source,
            "plugin_id": spec.plugin_id,
            "config_schema": spec.config_schema or {},
        }
        for spec in registry.providers.values()
        if registry.is_provider_kind_available(spec.kind)
    ]


@router.get("/presets")
async def list_presets():
    return [
        {
            "kind": kind,
            "name": spec["name"],
            "title": spec.get("title") or spec["name"],
            "base_url": spec["base_url"],
            "needs_key": "default_api_key" not in spec,
        }
        for kind, spec in registry.presets.items()
        if registry.is_preset_available(kind)
    ]


class PresetIn(BaseModel):
    api_key: str | None = None
    make_default: bool = True


@router.post("/presets/{kind}")
async def create_from_preset(kind: str, body: PresetIn = PresetIn()):
    preset = registry.presets.get(kind)
    if not preset:
        raise HTTPException(status_code=404, detail={"code": "preset.not_found"})
    if not registry.is_preset_available(kind):
        raise HTTPException(
            status_code=403,
            detail={"code": "plugin.disabled", "message": f"预设 {kind} 对应的插件已停用"},
        )
    key = body.api_key or preset.get("default_api_key") or ""
    if "default_api_key" not in preset and not key:
        raise HTTPException(status_code=400, detail={"code": "provider.auth", "message": "API Key 必填"})
    try:
        provider = await apply_preset(kind, api_key=key, make_default=body.make_default)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider.sync_failed", "message": str(exc)},
        ) from exc
    item = provider_public(provider)
    item["models"] = [model_public(m) for m in await LlmModel.filter(provider_id=provider.id, enabled=True)]
    return item


@router.get("/providers")
async def list_providers():
    rows = await LlmProvider.all()
    out = []
    for p in rows:
        if not registry.is_provider_kind_available(p.kind):
            continue
        item = provider_public(p)
        models = await LlmModel.filter(provider_id=p.id, enabled=True)
        item["models"] = [model_public(m) for m in models]
        out.append(item)
    return out


@router.post("/providers")
async def create_provider(body: ProviderIn):
    require_provider_kind(body.kind)
    row = await LlmProvider.create(
        name=body.name,
        kind=body.kind,
        base_url=normalize_base_url_for_kind(body.kind, body.base_url),
        api_key_encrypted=encrypt_secret(body.api_key or ""),
        extra_headers=body.extra_headers,
        enabled=body.enabled,
    )
    if body.sync_models:
        try:
            await sync_provider_models(row, make_default=body.make_default)
        except Exception as exc:
            await row.delete()
            raise HTTPException(
                status_code=400,
                detail={"code": "provider.sync_failed", "message": str(exc)},
            ) from exc
    item = provider_public(row)
    item["models"] = [model_public(m) for m in await LlmModel.filter(provider_id=row.id, enabled=True)]
    return item


@router.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, body: dict):
    row = await LlmProvider.get_or_none(id=provider_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    if "kind" in body:
        require_provider_kind(str(body["kind"]))
    await require_provider_available(row)
    if "name" in body:
        row.name = body["name"]
    if "kind" in body:
        row.kind = body["kind"]
    if "base_url" in body:
        kind = str(body.get("kind") or row.kind)
        row.base_url = normalize_base_url_for_kind(kind, str(body["base_url"]))
    if "api_key" in body and body["api_key"]:
        row.api_key_encrypted = encrypt_secret(body["api_key"])
    if "extra_headers" in body:
        row.extra_headers = body["extra_headers"]
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    await row.save()
    return provider_public(row)


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    row = await LlmProvider.get_or_none(id=provider_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    await LlmModel.filter(provider_id=provider_id).delete()
    await row.delete()
    return {"ok": True}


@router.post("/providers/{provider_id}/sync-models")
async def sync_models(provider_id: str, body: SyncModelsIn = SyncModelsIn()):
    provider = await LlmProvider.get_or_none(id=provider_id)
    await require_provider_available(provider)
    try:
        models = await sync_provider_models(
            provider,
            make_default=body.make_default,
            disable_missing=body.disable_missing,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider.sync_failed", "message": str(exc)},
        ) from exc
    return {
        "ok": True,
        "count": len(models),
        "models": [model_public(m) for m in models],
    }


@router.get("/providers/{provider_id}/remote-models")
async def list_remote_models(provider_id: str):
    provider = await LlmProvider.get_or_none(id=provider_id)
    await require_provider_available(provider)
    try:
        models = await fetch_remote_models(provider)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider.sync_failed", "message": str(exc)},
        ) from exc
    return {"models": models}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str):
    provider = await LlmProvider.get_or_none(id=provider_id)
    await require_provider_available(provider)

    rows = await LlmModel.filter(provider_id=provider_id)
    if not rows:
        try:
            await sync_provider_models(provider)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "provider.sync_failed", "message": str(exc)},
            ) from exc

    async def gen():
        try:
            async for event in iter_probe_provider_models(provider):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/providers/{provider_id}/balance")
async def provider_balance(provider_id: str):
    from code_agent.llm.adapters import get_llm_adapter

    provider = await LlmProvider.get_or_none(id=provider_id)
    await require_provider_available(provider)
    adapter = get_llm_adapter(provider)
    fetch_balance = getattr(adapter, "fetch_balance", None)
    if not getattr(adapter, "supports_balance", False) or not callable(fetch_balance):
        raise HTTPException(
            status_code=400,
            detail={"code": "provider.balance_unsupported", "message": "该提供商不支持查询余额"},
        )
    try:
        return await fetch_balance(provider)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider.balance", "message": str(exc)},
        ) from exc


@router.post("/models")
async def create_model(body: ModelIn):
    provider = await LlmProvider.get_or_none(id=body.provider_id)
    await require_provider_available(provider)
    if body.is_default:
        await LlmModel.all().update(is_default=False)
    from code_agent.llm.capabilities import default_params, infer_capabilities

    caps = infer_capabilities(body.model_id)
    vision = body.supports_vision or bool(caps.get("vision", {}).get("supported"))
    # Keep capabilities.vision in sync with the persisted flag
    caps.setdefault("vision", {})["supported"] = vision
    row = await LlmModel.create(
        provider_id=body.provider_id,
        model_id=body.model_id,
        display_name=body.display_name or body.model_id,
        context_window=body.context_window,
        supports_tools=body.supports_tools,
        supports_vision=vision,
        capabilities_json=caps,
        params_json=body.params or default_params(caps),
        is_default=body.is_default,
    )
    return model_public(row)


@router.patch("/models/{model_id}")
async def update_model(model_id: str, body: dict):
    row = await LlmModel.get_or_none(id=model_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "model.not_found"})
    if body.get("is_default"):
        await LlmModel.all().update(is_default=False)
        row.is_default = True
    for field in ("display_name", "model_id", "context_window", "supports_tools", "supports_vision", "enabled"):
        if field in body:
            setattr(row, field, body[field])
    if "model_id" in body or "supports_vision" in body:
        from code_agent.llm.capabilities import infer_capabilities

        caps = infer_capabilities(row.model_id)
        if "supports_vision" in body:
            caps.setdefault("vision", {})["supported"] = bool(row.supports_vision)
        else:
            row.supports_vision = bool(caps.get("vision", {}).get("supported"))
        row.capabilities_json = {**(row.capabilities_json or {}), **caps}
    if "params" in body and isinstance(body["params"], dict):
        row.params_json = body["params"]
    if "capabilities" in body and isinstance(body["capabilities"], dict):
        from code_agent.llm.capabilities import apply_capability_overrides

        caps = dict(row.capabilities_json or {})
        incoming = body["capabilities"]
        overrides = dict(caps.get("overrides") or {})
        for key in ("tools", "vision", "thinking"):
            spec = incoming.get(key)
            if isinstance(spec, dict) and "supported" in spec:
                overrides[key] = bool(spec["supported"])
            elif isinstance(spec, bool):
                overrides[key] = spec
        caps.update({k: v for k, v in incoming.items() if k not in {"availability"}})
        row.capabilities_json = apply_capability_overrides(caps, overrides)
        row.supports_tools = bool((row.capabilities_json.get("tools") or {}).get("supported"))
        row.supports_vision = bool((row.capabilities_json.get("vision") or {}).get("supported"))
    await row.save()
    return model_public(row)


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    row = await LlmModel.get_or_none(id=model_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "model.not_found"})
    await row.delete()
    return {"ok": True}
