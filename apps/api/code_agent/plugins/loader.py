from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from code_agent.config import settings
from code_agent.plugins.base import PluginInfo, registry


def _load_file(path: Path) -> None:
    name = f"code_agent_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if hasattr(module, "register"):
        module.register(registry)
        registry.register_plugin(
            PluginInfo(
                plugin_id=path.stem,
                source=str(path),
                title=getattr(module, "PLUGIN_TITLE", path.stem),
                description=getattr(module, "PLUGIN_DESCRIPTION", ""),
                kind="python",
            )
        )


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
        for path in sorted(root.glob("*.py")):
            if path.name.startswith("_"):
                continue
            key = path.stem
            if key in seen:
                continue
            seen.add(key)
            try:
                _load_file(path)
            except Exception as exc:  # plugin must not crash boot
                registry.register_plugin(
                    PluginInfo(
                        plugin_id=path.stem,
                        source=str(path),
                        title=path.stem,
                        description=f"failed to load: {exc}",
                        enabled=False,
                        kind="python",
                    )
                )
