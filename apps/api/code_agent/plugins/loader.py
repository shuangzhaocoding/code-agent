from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from code_agent.config import settings
from code_agent.plugins.base import PluginInfo, registry
from code_agent.plugins.meta import apply_plugin_meta, meta_from_mapping

_active_workspace_root: str | None = None


def active_workspace_root() -> str | None:
    return _active_workspace_root


def workspace_plugins_dir(workspace_root: str) -> Path:
    return Path(workspace_root).expanduser().resolve() / ".code-agent" / "plugins"


def _normalize_workspace_root(workspace_root: str) -> str:
    return str(Path(workspace_root).expanduser().resolve())


def _origin_for(root: Path, workspace_root: str | None) -> str:
    repo = settings.repo_root / "plugins"
    user = Path(settings.get("paths.user_plugins", "~/.code-agent/plugins")).expanduser()
    if root == repo:
        return "repo"
    if workspace_root and root == Path(workspace_root) / ".code-agent" / "plugins":
        return "workspace"
    if root == user:
        return "user"
    return "python"


def _purge_plugin_modules(plugin_ids: list[str]) -> None:
    for plugin_id in plugin_ids:
        mod_name = f"code_agent_plugin_{plugin_id.replace('.', '_')}"
        sys.modules.pop(mod_name, None)


def _load_module(path: Path, plugin_id: str) -> None:
    name = f"code_agent_plugin_{plugin_id.replace('.', '_')}"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = registry.loading_plugin_id
    registry.loading_plugin_id = plugin_id
    try:
        spec.loader.exec_module(module)
        if hasattr(module, "register"):
            module.register(registry)
        if plugin_id not in registry.plugins:
            registry.register_plugin(
                PluginInfo(
                    plugin_id=plugin_id,
                    source=str(path),
                    title=getattr(module, "PLUGIN_TITLE", plugin_id),
                    description=getattr(module, "PLUGIN_DESCRIPTION", ""),
                    kind=getattr(module, "PLUGIN_KIND", "python"),
                    version=str(getattr(module, "PLUGIN_VERSION", "1.0.0")),
                    api=int(getattr(module, "PLUGIN_API", 1) or 1),
                )
            )
        info = registry.plugins.get(plugin_id)
        if info is not None:
            apply_plugin_meta(info, module=module)
    finally:
        registry.loading_plugin_id = previous


def _load_file(path: Path, *, origin: str) -> None:
    _load_module(path, path.stem)
    info = registry.plugins.get(path.stem)
    if info is not None:
        info.source = str(path)
        info.origin = origin
        if not info.contributes:
            has_llm = any(s.plugin_id == path.stem for s in registry.providers.values())
            has_tools = any(
                s.plugin_id == path.stem or s.source in {path.stem, f"plugin:{path.stem}"}
                for s in registry.tools.values()
            )
            contrib: list[str] = []
            if has_llm:
                contrib.append("llm.provider")
            if has_tools:
                contrib.append("tools")
            info.contributes = tuple(contrib)


def _load_directory(path: Path, *, origin: str) -> None:
    manifest_path = path / "plugin.json"
    entry = path / "plugin.py"
    meta: dict = {}
    if manifest_path.exists():
        try:
            meta = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            registry.register_plugin(
                PluginInfo(
                    plugin_id=path.name,
                    source=str(path),
                    title=path.name,
                    description=f"invalid plugin.json: {exc}",
                    enabled=False,
                    kind="python",
                    origin=origin,
                    error=str(exc),
                )
            )
            return
    plugin_id = str(meta.get("id") or path.name)
    api = int(meta.get("api") or 1)
    if api > 1:
        registry.register_plugin(
            PluginInfo(
                plugin_id=plugin_id,
                source=str(path),
                title=str(meta.get("name") or path.name),
                description=f"unsupported plugin api {api}",
                enabled=False,
                kind="python",
                origin=origin,
                api=api,
                error=f"unsupported api {api}",
            )
        )
        return
    if not entry.exists():
        registry.register_plugin(
            PluginInfo(
                plugin_id=plugin_id,
                source=str(path),
                title=str(meta.get("name") or path.name),
                description="plugin.py is missing",
                enabled=False,
                kind="python",
                origin=origin,
                error="plugin.py is missing",
            )
        )
        return
    _load_module(entry, plugin_id)
    info = registry.plugins.get(plugin_id)
    if info is None:
        registry.register_plugin(
            PluginInfo(
                plugin_id=plugin_id,
                source=str(path),
                title=str(meta.get("name") or plugin_id),
                description=str(meta.get("description") or ""),
                kind="python",
                origin=origin,
            )
        )
        info = registry.plugins[plugin_id]
    info.source = str(path)
    info.origin = origin
    if meta.get("name"):
        info.title = str(meta["name"])
    if meta.get("description"):
        info.description = str(meta["description"])
    if meta.get("version"):
        info.version = str(meta["version"])
    if meta.get("kind"):
        info.kind = str(meta["kind"])
    contributes = meta.get("contributes")
    if isinstance(contributes, list):
        info.contributes = tuple(str(x) for x in contributes)
    apply_plugin_meta(info, meta=meta_from_mapping(meta))


def _register_load_error(path: Path, *, origin: str, plugin_id: str, exc: Exception) -> None:
    registry.register_plugin(
        PluginInfo(
            plugin_id=plugin_id,
            source=str(path),
            title=plugin_id,
            description=f"failed to load: {exc}",
            enabled=False,
            kind="python",
            origin=origin,
            error=str(exc),
        )
    )


def _load_plugin_root(
    root: Path,
    *,
    origin: str,
    workspace_root: str | None,
    seen: set[str],
    reserved_ids: set[str] | None = None,
) -> list[str]:
    """Scan one plugin directory. Returns loaded plugin ids."""
    reserved = reserved_ids or set()
    loaded: list[str] = []
    if not root.exists():
        return loaded

    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        key = path.stem
        if key in seen or key in reserved:
            continue
        seen.add(key)
        try:
            _load_file(path, origin=origin)
            loaded.append(key)
        except Exception as exc:  # plugin must not crash host
            _register_load_error(path, origin=origin, plugin_id=key, exc=exc)
            loaded.append(key)

    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("_") or path.name in seen:
            continue
        if not (path / "plugin.py").exists() and not (path / "plugin.json").exists():
            continue
        if path.name in reserved:
            continue
        seen.add(path.name)
        try:
            _load_directory(path, origin=origin)
            loaded.append(path.name)
        except Exception as exc:
            _register_load_error(path, origin=origin, plugin_id=path.name, exc=exc)
            loaded.append(path.name)

    return loaded


def load_plugins(workspace_root: str | None = None) -> None:
    """Load repo + user plugins, optionally including a workspace directory."""
    roots = [
        settings.repo_root / "plugins",
        Path(settings.get("paths.user_plugins", "~/.code-agent/plugins")).expanduser(),
    ]
    if workspace_root:
        roots.append(workspace_plugins_dir(workspace_root))
    seen: set[str] = set()
    for root in roots:
        origin = _origin_for(root, workspace_root)
        _load_plugin_root(root, origin=origin, workspace_root=workspace_root, seen=seen)


def load_workspace_plugins(workspace_root: str) -> list[str]:
    """Load only `.code-agent/plugins` for a workspace (repo/user ids win)."""
    reserved = set(registry.plugins.keys())
    seen: set[str] = set()
    root = workspace_plugins_dir(workspace_root)
    return _load_plugin_root(
        root,
        origin="workspace",
        workspace_root=workspace_root,
        seen=seen,
        reserved_ids=reserved,
    )


def unload_workspace_plugins() -> list[str]:
    """Drop all workspace-scoped plugins from the registry."""
    global _active_workspace_root
    removed = registry.unload_by_origin("workspace")
    _purge_plugin_modules(removed)
    _active_workspace_root = None
    return removed


async def activate_workspace_plugins(workspace_root: str) -> dict:
    """Hot-reload workspace plugins when a workspace is opened or switched."""
    global _active_workspace_root

    normalized = _normalize_workspace_root(workspace_root)
    removed = unload_workspace_plugins()
    loaded = load_workspace_plugins(normalized)
    await apply_plugin_states(plugin_ids=loaded)
    settings.reload(normalized)
    _active_workspace_root = normalized
    return {
        "workspace_root": normalized,
        "removed": removed,
        "loaded": loaded,
        "plugins": [
            registry.plugin_public(info)
            for info in registry.plugins.values()
            if info.origin == "workspace"
        ],
    }


async def apply_plugin_states(plugin_ids: list[str] | None = None) -> None:
    from code_agent.db.models import PluginState

    try:
        rows = {row.plugin_id: row for row in await PluginState.all()}
    except Exception:
        return
    targets = (
        [registry.plugins[pid] for pid in plugin_ids if pid in registry.plugins]
        if plugin_ids is not None
        else list(registry.plugins.values())
    )
    for info in targets:
        row = rows.get(info.plugin_id)
        if row is not None:
            registry.set_plugin_enabled(info.plugin_id, row.enabled)
