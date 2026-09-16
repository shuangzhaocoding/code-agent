from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from code_agent.config import (
    SETTINGS_SCHEMA,
    STORAGE_SETTING_KEYS,
    UPLOADS_SETTING_KEYS,
    WORKSPACE_SETTING_KEYS,
    merge_user_config,
    merge_workspace_config,
    settings,
    workspace_setting_values,
)
from code_agent.db.models import Setting, Workspace
from code_agent.plugins.base import registry

router = APIRouter(prefix="/api", tags=["settings"])

# Empty string means "use default / env", not an intentional stored value.
_CLEAR_ON_EMPTY = frozenset(
    {
        "terminal.shell",
        "python.interpreter",
        "uploads.dir",
        "storage.postgres_url",
        "storage.redis_url",
        "storage.checkpoint_postgres_url",
        "server.access_password",
    }
)


def _clear_live_setting(key: str) -> None:
    settings.unset_dotted(key)


def _schema_with_defaults() -> dict[str, Any]:
    return SETTINGS_SCHEMA


async def _load_user_values() -> tuple[dict[str, Any], dict[str, Any]]:
    stored = {s.key: s.value_json for s in await Setting.all()}
    values: dict[str, Any] = {}
    for key, spec in SETTINGS_SCHEMA["properties"].items():
        if key in WORKSPACE_SETTING_KEYS:
            continue
        if key in stored:
            values[key] = stored[key]
        elif settings.get(key) is not None:
            values[key] = settings.get(key)
        else:
            values[key] = spec.get("default")
    return values, stored


async def _load_workspace_values(workspace_id: str | None) -> tuple[dict[str, Any], Workspace | None]:
    if not workspace_id:
        return {}, None
    ws = await Workspace.get_or_none(id=workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    from code_agent.workspace.backend import get_workspace_backend, workspace_is_ssh

    values: dict[str, Any] = {}
    if workspace_is_ssh(ws):
        backend = await get_workspace_backend(ws)
        try:
            import yaml

            try:
                text = await backend.read_text(".code-agent/config.yaml")
            except Exception:
                text = ""
            cfg = yaml.safe_load(text) if text.strip() else {}
            if not isinstance(cfg, dict):
                cfg = {}
            for key in WORKSPACE_SETTING_KEYS:
                cur: Any = cfg
                ok = True
                for part in key.split("."):
                    if not isinstance(cur, dict) or part not in cur:
                        ok = False
                        break
                    cur = cur[part]
                if ok and cur is not None and cur != "":
                    values[key] = cur
        finally:
            await backend.close()
    else:
        values = workspace_setting_values(ws.root_path)

    # Fall back to legacy global DB value so existing installs keep working until saved.
    for key in WORKSPACE_SETTING_KEYS:
        if key in values:
            continue
        row = await Setting.get_or_none(key=key)
        if row is not None and row.value_json not in (None, ""):
            values[key] = row.value_json
        elif settings.get(key) not in (None, ""):
            values[key] = settings.get(key)
        else:
            values[key] = SETTINGS_SCHEMA["properties"][key].get("default", "")
    for key in WORKSPACE_SETTING_KEYS:
        values.setdefault(key, SETTINGS_SCHEMA["properties"][key].get("default", ""))
    return values, ws


async def _write_workspace_values(ws: Workspace, patch: dict[str, Any]) -> None:
    from code_agent.workspace.backend import get_workspace_backend, workspace_is_ssh

    if not patch:
        return
    if workspace_is_ssh(ws):
        import yaml

        backend = await get_workspace_backend(ws)
        try:
            try:
                text = await backend.read_text(".code-agent/config.yaml")
            except Exception:
                text = ""
            existing = yaml.safe_load(text) if text.strip() else {}
            if not isinstance(existing, dict):
                existing = {}
            for dotted, value in patch.items():
                parts = [p for p in dotted.split(".") if p]
                if not parts:
                    continue
                cur: dict[str, Any] = existing
                for part in parts[:-1]:
                    nxt = cur.get(part)
                    if not isinstance(nxt, dict):
                        nxt = {}
                        cur[part] = nxt
                    cur = nxt
                if value is None or value == "":
                    cur.pop(parts[-1], None)
                else:
                    cur[parts[-1]] = value
            await backend.mkdir(".code-agent")
            dumped = yaml.safe_dump(
                existing, allow_unicode=True, sort_keys=False, default_flow_style=False
            )
            await backend.write_text(".code-agent/config.yaml", dumped)
        finally:
            await backend.close()
    else:
        merge_workspace_config(ws.root_path, patch)

    # Migrate: drop legacy global DB copies of workspace keys.
    for key in patch:
        if key not in WORKSPACE_SETTING_KEYS:
            continue
        row = await Setting.get_or_none(key=key)
        if row:
            await row.delete()
        _clear_live_setting(key)


@router.get("/settings")
async def get_settings(workspace_id: str | None = None):
    from code_agent.runtime.profile import runtime_public
    from code_agent.storage.backends import storage_public
    from code_agent.middleware.access_password import access_password_enabled

    user_values, stored = await _load_user_values()
    workspace_values, _ws = await _load_workspace_values(workspace_id)

    # Effective merged view (workspace keys overlay user/legacy).
    values = dict(user_values)
    for key in WORKSPACE_SETTING_KEYS:
        if key in workspace_values:
            values[key] = workspace_values[key]
        else:
            values[key] = SETTINGS_SCHEMA["properties"][key].get("default", "")

    # Never leak the access password; only signal whether a password is stored.
    raw_pw = stored.get("server.access_password")
    if raw_pw is None:
        raw_pw = settings.get("server.access_password")
    password_set = bool(str(raw_pw or "").strip())
    values["server.access_password"] = ""
    user_values["server.access_password"] = ""
    if "server.access_password_enabled" not in values or values.get("server.access_password_enabled") is None:
        values["server.access_password_enabled"] = False
        user_values["server.access_password_enabled"] = False
    return {
        "schema": _schema_with_defaults(),
        "values": values,
        "user_values": user_values,
        "workspace_values": workspace_values,
        "workspace_keys": sorted(WORKSPACE_SETTING_KEYS),
        "workspace_id": workspace_id,
        "access_password_set": password_set,
        "access_password_enabled": access_password_enabled(),
        "config": settings.raw(),
        "runtime": runtime_public(),
        "storage": storage_public(),
        "uploads_resolved": str(settings.uploads_dir),
    }


@router.patch("/settings")
async def patch_settings(body: dict[str, Any], workspace_id: str | None = None):
    from code_agent.middleware.access_password import access_password_plain, store_access_password
    from code_agent.streaming.run_capacity import reset_run_slots

    storage_patch: dict[str, Any] = {}
    uploads_patch: dict[str, Any] = {}
    ws_id = workspace_id or body.pop("workspace_id", None)
    scope = str(body.pop("scope", "") or "").strip().lower()
    # Remaining body keys are setting patches.
    patch_body = {k: v for k, v in body.items() if k in SETTINGS_SCHEMA["properties"]}

    # Reject enabling the gate without a password (existing or newly provided).
    if patch_body.get("server.access_password_enabled") is True:
        incoming_pw = patch_body.get("server.access_password")
        has_new = isinstance(incoming_pw, str) and incoming_pw.strip() and incoming_pw.strip() not in {"********", "****"}
        if not has_new and not access_password_plain():
            raise HTTPException(
                status_code=400,
                detail={"code": "auth.password_required", "message": "启用访问口令前请先设置口令"},
            )

    workspace_patch: dict[str, Any] = {}
    for key, value in list(patch_body.items()):
        is_workspace_key = key in WORKSPACE_SETTING_KEYS
        if scope == "workspace" or (not scope and is_workspace_key):
            if not is_workspace_key:
                continue
            if not ws_id:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "settings.workspace_required", "message": "工作空间设置需要先打开工作区"},
                )
            workspace_patch[key] = "" if value is None else value
            continue

        if is_workspace_key:
            # User-scope PATCH should not write workspace keys to the global DB anymore.
            continue

        if key == "server.access_password":
            # Empty / placeholder means clear; non-empty stores encrypted.
            text = "" if value is None else str(value)
            if text in {"", "********", "****"}:
                value = ""
            else:
                value = store_access_password(text)

        clear = key in _CLEAR_ON_EMPTY and (value is None or value == "")
        if clear:
            row = await Setting.get_or_none(key=key)
            if row:
                await row.delete()
            _clear_live_setting(key)
            parts = key.split(".")
            if key in STORAGE_SETTING_KEYS and len(parts) == 2:
                storage_patch[parts[1]] = ""
            if key in UPLOADS_SETTING_KEYS and len(parts) == 2:
                uploads_patch[parts[1]] = ""
            continue

        row = await Setting.get_or_none(key=key)
        if row:
            row.value_json = value
            await row.save()
        else:
            await Setting.create(key=key, value_json=value)
        settings.set_dotted(key, value)
        parts = key.split(".")
        if key in STORAGE_SETTING_KEYS and len(parts) == 2:
            storage_patch[parts[1]] = value
        if key in UPLOADS_SETTING_KEYS and len(parts) == 2:
            uploads_patch[parts[1]] = value
        if key == "agent.max_concurrent_runs":
            reset_run_slots()

    if workspace_patch:
        ws = await Workspace.get_or_none(id=ws_id)
        if ws is None:
            raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
        await _write_workspace_values(ws, workspace_patch)

    if storage_patch:
        merge_user_config("storage", storage_patch)
    if uploads_patch:
        merge_user_config("uploads", uploads_patch)
        settings.refresh_uploads_dir()
    return await get_settings(workspace_id=ws_id)


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
