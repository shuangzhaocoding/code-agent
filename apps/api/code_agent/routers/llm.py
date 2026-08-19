from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.crypto import encrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.hub import PROVIDER_PRESETS, apply_preset, get_chat_model, model_public, provider_public
from code_agent.plugins.base import registry

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ProviderIn(BaseModel):
    name: str
    kind: str = "openai_compat"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    extra_headers: dict = Field(default_factory=dict)
    enabled: bool = True


class ModelIn(BaseModel):
    provider_id: str
    model_id: str
    display_name: str | None = None
    context_window: int = 128000
    supports_tools: bool = True
    supports_vision: bool = False
    is_default: bool = False


@router.get("/kinds")
async def kinds():
    return [
        {"kind": spec.kind, "title": spec.title, "source": spec.source}
        for spec in registry.providers.values()
        if spec.enabled
    ]


@router.get("/presets")
async def list_presets():
    return [
        {
            "kind": kind,
            "name": spec["name"],
            "title": spec.get("title") or spec["name"],
            "base_url": spec["base_url"],
            "models": spec["models"],
            "needs_key": "default_api_key" not in spec,
        }
        for kind, spec in PROVIDER_PRESETS.items()
    ]


class PresetIn(BaseModel):
    api_key: str | None = None
    make_default: bool = True


@router.post("/presets/{kind}")
async def create_from_preset(kind: str, body: PresetIn = PresetIn()):
    if kind not in PROVIDER_PRESETS:
        raise HTTPException(status_code=404, detail={"code": "preset.not_found"})
    preset = PROVIDER_PRESETS[kind]
    key = body.api_key or preset.get("default_api_key") or ""
    if "default_api_key" not in preset and not key:
        raise HTTPException(status_code=400, detail={"code": "provider.auth", "message": "API Key 必填"})
    provider = await apply_preset(kind, api_key=key, make_default=body.make_default)
    item = provider_public(provider)
    item["models"] = [model_public(m) for m in await LlmModel.filter(provider_id=provider.id)]
    return item


@router.get("/providers")
async def list_providers():
    rows = await LlmProvider.all()
    out = []
    for p in rows:
        item = provider_public(p)
        models = await LlmModel.filter(provider_id=p.id)
        item["models"] = [model_public(m) for m in models]
        out.append(item)
    return out


@router.post("/providers")
async def create_provider(body: ProviderIn):
    row = await LlmProvider.create(
        name=body.name,
        kind=body.kind,
        base_url=body.base_url.rstrip("/"),
        api_key_encrypted=encrypt_secret(body.api_key or ""),
        extra_headers=body.extra_headers,
        enabled=body.enabled,
    )
    return provider_public(row)


@router.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, body: dict):
    row = await LlmProvider.get_or_none(id=provider_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    if "name" in body:
        row.name = body["name"]
    if "kind" in body:
        row.kind = body["kind"]
    if "base_url" in body:
        row.base_url = str(body["base_url"]).rstrip("/")
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


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str):
    provider = await LlmProvider.get_or_none(id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    model = await LlmModel.filter(provider_id=provider_id).first()
    if not model:
        raise HTTPException(status_code=400, detail={"code": "model.missing", "message": "Add a model first"})
    chat, _ = await get_chat_model(str(model.id))
    if chat is None:
        raise HTTPException(status_code=400, detail={"code": "provider.invalid"})
    try:
        msg = await chat.ainvoke("Reply with the single word pong.")
        return {"ok": True, "reply": getattr(msg, "content", str(msg))[:500]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "provider.auth", "message": str(exc)})


@router.post("/models")
async def create_model(body: ModelIn):
    provider = await LlmProvider.get_or_none(id=body.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    if body.is_default:
        await LlmModel.all().update(is_default=False)
    row = await LlmModel.create(
        provider_id=body.provider_id,
        model_id=body.model_id,
        display_name=body.display_name or body.model_id,
        context_window=body.context_window,
        supports_tools=body.supports_tools,
        supports_vision=body.supports_vision,
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
    await row.save()
    return model_public(row)


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    row = await LlmModel.get_or_none(id=model_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "model.not_found"})
    await row.delete()
    return {"ok": True}
