from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from code_agent.config import settings
from code_agent.plugins.base import PluginInfo, registry
from code_agent.plugins.meta import apply_plugin_meta, meta_from_mapping


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


def _load_module(path: Path, plugin_id: str) -> None:
    name = f"code_agent_plugin_{plugin_id.replace('.', '_')}"
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


def load_plugins(workspace_root: str | None = None) -> None:
    roots = [
        settings.repo_root / "plugins",
        Path(settings.get("paths.user_plugins", "~/.code-agent/plugins")).expanduser(),
    ]
    if workspace_root:
        roots.append(Path(workspace_root) / ".code-agent" / "plugins")
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        origin = _origin_for(root, workspace_root)
        for path in sorted(root.glob("*.py")):
            if path.name.startswith("_"):
                continue
            key = path.stem
            if key in seen:
                continue
            seen.add(key)
            try:
                _load_file(path, origin=origin)
            except Exception as exc:  # plugin must not crash boot
                registry.register_plugin(
                    PluginInfo(
                        plugin_id=path.stem,
                        source=str(path),
                        title=path.stem,
                        description=f"failed to load: {exc}",
                        enabled=False,
                        kind="python",
                        origin=origin,
                        error=str(exc),
                    )
                )
        for path in sorted(root.iterdir()):
            if not path.is_dir() or path.name.startswith("_") or path.name in seen:
                continue
            if not (path / "plugin.py").exists() and not (path / "plugin.json").exists():
                continue
            seen.add(path.name)
            try:
                _load_directory(path, origin=origin)
            except Exception as exc:
                registry.register_plugin(
                    PluginInfo(
                        plugin_id=path.name,
                        source=str(path),
                        title=path.name,
                        description=f"failed to load: {exc}",
                        enabled=False,
                        kind="python",
                        origin=origin,
                        error=str(exc),
                    )
                )


async def apply_plugin_states() -> None:
    from code_agent.db.models import PluginState

    rows = {row.plugin_id: row for row in await PluginState.all()}
    for info in registry.plugins.values():
        row = rows.get(info.plugin_id)
        if row is not None:
            registry.set_plugin_enabled(info.plugin_id, row.enabled)
