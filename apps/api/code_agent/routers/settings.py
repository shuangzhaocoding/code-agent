from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from code_agent.config import SETTINGS_SCHEMA, settings
from code_agent.db.models import Setting
from code_agent.plugins.base import registry

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    stored = {s.key: s.value_json for s in await Setting.all()}
    values = {}
    for key, spec in SETTINGS_SCHEMA["properties"].items():
        values[key] = stored[key] if key in stored else spec.get("default")
    return {"schema": SETTINGS_SCHEMA, "values": values, "config": settings.raw()}


@router.patch("/settings")
async def patch_settings(body: dict[str, Any]):
    for key, value in body.items():
        if key not in SETTINGS_SCHEMA["properties"]:
            continue
        row = await Setting.get_or_none(key=key)
        if row:
            row.value_json = value
            await row.save()
        else:
            await Setting.create(key=key, value_json=value)
        # overlay live config for known prefixes
        parts = key.split(".")
        if len(parts) == 2:
            bucket = settings._cfg.setdefault(parts[0], {})
            bucket[parts[1]] = value
    return await get_settings()


@router.get("/plugins")
async def list_plugins():
    tools = [
        {
            "name": spec.name,
            "source": spec.source,
            "enabled": spec.enabled,
            "modes": list(spec.modes),
            "description": spec.description,
        }
        for spec in registry.tools.values()
    ]
    plugins = [
        {
            "id": p.plugin_id,
            "title": p.title,
            "source": p.source,
            "enabled": p.enabled,
            "description": p.description,
            "kind": p.kind,
        }
        for p in registry.plugins.values()
    ]
    return {"tools": tools, "plugins": plugins, "providers": [p.kind for p in registry.providers.values()]}


@router.patch("/plugins/tools/{name}")
async def toggle_tool(name: str, body: dict):
    spec = registry.tools.get(name)
    if spec:
        spec.enabled = bool(body.get("enabled", True))
    return {"ok": True, "name": name, "enabled": spec.enabled if spec else None}


@router.get("/layout")
async def get_layout(workspace_id: str | None = None):
    key = f"layout.{workspace_id or 'default'}"
    row = await Setting.get_or_none(key=key)
    return {"layout": row.value_json if row else None}


@router.put("/layout")
async def save_layout(body: dict):
    workspace_id = body.get("workspace_id") or "default"
    key = f"layout.{workspace_id}"
    layout = body.get("layout")
    row = await Setting.get_or_none(key=key)
    if row:
        row.value_json = layout
        await row.save()
    else:
        await Setting.create(key=key, value_json=layout)
    return {"ok": True}
