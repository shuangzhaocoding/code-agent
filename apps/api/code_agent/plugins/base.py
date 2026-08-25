from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from langchain_core.tools import BaseTool


class LlmAdapter(Protocol):
    """Standard contract for a model-provider plugin.

    Third-party plugins implement this and call ``registry.register_llm_adapter``.
    The host never talks to a vendor API except through these methods.
    """

    kind: str
    title: str
    description: str
    config_schema: dict[str, Any]
    presets: list[dict[str, Any]]

    def create_chat_model(self, provider: Any, model: Any) -> Any: ...

    async def list_models(self, provider: Any) -> list[dict[str, Any]]: ...

    async def probe_model(self, provider: Any, model_id: str) -> dict[str, Any]: ...

    def apply_thinking(self, chat: Any, provider: Any, model: Any, level: str) -> Any: ...

    def normalize_base_url(self, base_url: str) -> str: ...


@dataclass
class ToolSpec:
    name: str
    tool: BaseTool
    source: str
    enabled: bool = True
    modes: tuple[str, ...] = ("ask", "agent", "plan")
    description: str = ""
    plugin_id: str = ""


@dataclass
class ProviderSpec:
    kind: str
    factory: Callable[..., Any]
    source: str
    title: str
    enabled: bool = True
    plugin_id: str = ""
    adapter: Any = None
    config_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    plugin_id: str
    source: str
    title: str
    description: str = ""
    enabled: bool = True
    kind: str = "generic"
    version: str = "1.0.0"
    api: int = 1
    origin: str = "python"
    contributes: tuple[str, ...] = ()
    error: str = ""
    author: str = ""
    homepage: str = ""
    repository: str = ""
    license: str = ""
    icon: str = ""
    icon_url: str = ""
    accent: str = ""
    keywords: tuple[str, ...] = ()


class PluginRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, ToolSpec] = {}
        self.providers: dict[str, ProviderSpec] = {}
        self.plugins: dict[str, PluginInfo] = {}
        self.presets: dict[str, dict[str, Any]] = {}
        self.layout_presets: dict[str, Any] = {}
        self.loading_plugin_id: str = ""

    def register_tool(
        self,
        tool: BaseTool,
        source: str,
        modes: tuple[str, ...] = ("ask", "agent", "plan"),
        plugin_id: str | None = None,
    ) -> None:
        pid = plugin_id or self.loading_plugin_id or ""
        self.tools[tool.name] = ToolSpec(
            name=tool.name,
            tool=tool,
            source=source,
            modes=modes,
            description=tool.description or "",
            plugin_id=pid,
        )

    def register_provider(self, spec: ProviderSpec) -> None:
        if not spec.plugin_id:
            spec.plugin_id = self.loading_plugin_id
        self.providers[spec.kind] = spec

    def register_plugin(self, info: PluginInfo) -> None:
        self.plugins[info.plugin_id] = info

    def register_preset(self, kind: str, preset: dict[str, Any], plugin_id: str = "") -> None:
        data = dict(preset)
        data.setdefault("kind", kind)
        if plugin_id:
            data["plugin_id"] = plugin_id
        self.presets[kind] = data

    def register_llm_adapter(
        self,
        adapter: LlmAdapter,
        *,
        plugin_id: str,
        kinds: list[tuple[str, str]] | None = None,
    ) -> None:
        """Register an LLM adapter and every vendor kind it exposes."""
        pairs = kinds or [(adapter.kind, adapter.title)]
        schema = dict(getattr(adapter, "config_schema", None) or {})
        for kind, title in pairs:
            self.register_provider(
                ProviderSpec(
                    kind=kind,
                    factory=adapter.create_chat_model,
                    source=plugin_id,
                    title=title,
                    plugin_id=plugin_id,
                    adapter=adapter,
                    config_schema=schema,
                )
            )
        for preset in getattr(adapter, "presets", None) or []:
            kind = str(preset.get("kind") or "")
            if kind:
                self.register_preset(kind, preset, plugin_id=plugin_id)

    def enabled_tools(self, mode: str) -> list[BaseTool]:
        out = []
        disabled_plugins = {
            p.plugin_id for p in self.plugins.values() if not p.enabled
        }
        for spec in self.tools.values():
            if not spec.enabled:
                continue
            if spec.plugin_id and spec.plugin_id in disabled_plugins:
                continue
            if mode not in spec.modes:
                continue
            if mode == "ask" and spec.name in {
                "write_file",
                "search_replace",
                "run_command",
                "delete_file",
            }:
                continue
            out.append(spec.tool)
        return out

    def _provider_spec_usable(self, spec: ProviderSpec | None) -> bool:
        if spec is None or not spec.enabled:
            return False
        if spec.plugin_id:
            plugin = self.plugins.get(spec.plugin_id)
            if plugin is not None and not plugin.enabled:
                return False
        return True

    def is_provider_kind_available(self, kind: str) -> bool:
        spec = self.providers.get(kind)
        if spec is not None:
            return self._provider_spec_usable(spec)
        fallback = self.providers.get("openai_compat")
        return self._provider_spec_usable(fallback)

    def is_preset_available(self, kind: str) -> bool:
        preset = self.presets.get(kind)
        if not preset:
            return False
        plugin_id = str(preset.get("plugin_id") or "")
        if plugin_id:
            plugin = self.plugins.get(plugin_id)
            if plugin is not None and not plugin.enabled:
                return False
        provider_kind = str(preset.get("kind") or kind)
        spec = self.providers.get(provider_kind)
        if spec is not None:
            return self._provider_spec_usable(spec)
        return self.is_provider_kind_available(provider_kind)

    def get_provider(self, kind: str) -> ProviderSpec | None:
        spec = self.providers.get(kind)
        if spec is not None:
            return spec if self._provider_spec_usable(spec) else None
        fallback = self.providers.get("openai_compat")
        return fallback if self._provider_spec_usable(fallback) else None

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> PluginInfo | None:
        info = self.plugins.get(plugin_id)
        if info is None:
            return None
        info.enabled = enabled
        for spec in self.providers.values():
            if spec.plugin_id == plugin_id:
                spec.enabled = enabled
        for spec in self.tools.values():
            if spec.plugin_id == plugin_id:
                spec.enabled = enabled
        return info

    def plugin_public(self, info: PluginInfo) -> dict[str, Any]:
        from code_agent.plugins.meta import plugin_meta_public

        providers = [
            {
                "kind": spec.kind,
                "title": spec.title,
                "enabled": spec.enabled,
                "config_schema": spec.config_schema or {},
            }
            for spec in self.providers.values()
            if spec.plugin_id == info.plugin_id
        ]
        tools = [
            {
                "name": spec.name,
                "description": spec.description,
                "enabled": spec.enabled,
                "modes": list(spec.modes),
            }
            for spec in self.tools.values()
            if spec.plugin_id == info.plugin_id
            or (not spec.plugin_id and spec.source in {info.plugin_id, f"plugin:{info.plugin_id}"})
        ]
        presets = [
            {
                "kind": kind,
                "name": preset.get("name") or kind,
                "title": preset.get("title") or preset.get("name") or kind,
                "base_url": preset.get("base_url") or "",
            }
            for kind, preset in self.presets.items()
            if preset.get("plugin_id") == info.plugin_id
        ]
        contributes = list(info.contributes)
        if not contributes:
            if providers:
                contributes.append("llm.provider")
            if tools:
                contributes.append("tools")
        return {
            "id": info.plugin_id,
            "title": info.title,
            "description": info.description,
            "source": info.source,
            "enabled": info.enabled,
            "kind": info.kind,
            "version": info.version,
            "api": info.api,
            "origin": info.origin,
            "contributes": contributes,
            "error": info.error or None,
            **plugin_meta_public(info),
            "providers": providers,
            "tools": tools,
            "presets": presets,
        }


registry = PluginRegistry()
