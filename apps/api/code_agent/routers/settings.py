from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from code_agent.config import SETTINGS_SCHEMA, STORAGE_SETTING_KEYS, merge_user_config, settings
from code_agent.db.models import Setting
from code_agent.plugins.base import registry

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    from code_agent.runtime.profile import runtime_public
    from code_agent.storage.backends import storage_public

    stored = {s.key: s.value_json for s in await Setting.all()}
    values = {}
    for key, spec in SETTINGS_SCHEMA["properties"].items():
        if key in stored:
            values[key] = stored[key]
        elif settings.get(key) is not None:
            values[key] = settings.get(key)
        else:
            values[key] = spec.get("default")
    return {
        "schema": SETTINGS_SCHEMA,
        "values": values,
        "config": settings.raw(),
        "runtime": runtime_public(),
        "storage": storage_public(),
    }


@router.patch("/settings")
async def patch_settings(body: dict[str, Any]):
    storage_patch: dict[str, Any] = {}
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
        if key in STORAGE_SETTING_KEYS and len(parts) == 2:
            storage_patch[parts[1]] = value
    if storage_patch:
        merge_user_config("storage", storage_patch)
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
            "plugin_id": spec.plugin_id,
        }
        for spec in registry.tools.values()
    ]
    plugins = [registry.plugin_public(p) for p in registry.plugins.values()]
    providers = [
        {
            "kind": spec.kind,
            "title": spec.title,
            "source": spec.source,
            "enabled": spec.enabled,
            "plugin_id": spec.plugin_id,
        }
        for spec in registry.providers.values()
    ]
    return {"tools": tools, "plugins": plugins, "providers": providers}


@router.patch("/plugins/tools/{name}")
async def toggle_tool(name: str, body: dict):
    spec = registry.tools.get(name)
    if spec:
        spec.enabled = bool(body.get("enabled", True))
    return {"ok": True, "name": name, "enabled": spec.enabled if spec else None}


@router.get("/plugins/{plugin_id}/icon")
async def get_plugin_icon(plugin_id: str):
    from code_agent.plugins.icon_assets import icon_media_type, resolve_icon_file

    info = registry.plugins.get(plugin_id)
    if info is None:
        raise HTTPException(status_code=404, detail={"code": "plugin.not_found"})
    path = resolve_icon_file(info)
    if path is None:
        raise HTTPException(status_code=404, detail={"code": "plugin.icon_not_found"})
    return FileResponse(path, media_type=icon_media_type(path))


@router.patch("/plugins/{plugin_id}")
async def patch_plugin(plugin_id: str, body: dict):
    from fastapi import HTTPException

    from code_agent.db.models import PluginState

    info = registry.plugins.get(plugin_id)
    if info is None:
        raise HTTPException(status_code=404, detail={"code": "plugin.not_found"})
    if "enabled" in body:
        enabled = bool(body.get("enabled"))
        registry.set_plugin_enabled(plugin_id, enabled)
        row = await PluginState.get_or_none(plugin_id=plugin_id)
        if row:
            row.enabled = enabled
            await row.save()
        else:
            await PluginState.create(plugin_id=plugin_id, enabled=enabled)
    return {"ok": True, "plugin": registry.plugin_public(info)}


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
