from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.tools import BaseTool


@dataclass
class ToolSpec:
    name: str
    tool: BaseTool
    source: str
    enabled: bool = True
    modes: tuple[str, ...] = ("ask", "agent", "plan")
    description: str = ""


@dataclass
class ProviderSpec:
    kind: str
    factory: Callable[..., Any]
    source: str
    title: str
    enabled: bool = True


@dataclass
class PluginInfo:
    plugin_id: str
    source: str
    title: str
    description: str = ""
    enabled: bool = True
    kind: str = "generic"


class PluginRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, ToolSpec] = {}
        self.providers: dict[str, ProviderSpec] = {}
        self.plugins: dict[str, PluginInfo] = {}
        self.layout_presets: dict[str, Any] = {}

    def register_tool(
        self,
        tool: BaseTool,
        source: str,
        modes: tuple[str, ...] = ("ask", "agent", "plan"),
    ) -> None:
        self.tools[tool.name] = ToolSpec(
            name=tool.name,
            tool=tool,
            source=source,
            modes=modes,
            description=tool.description or "",
        )

    def register_provider(self, spec: ProviderSpec) -> None:
        self.providers[spec.kind] = spec

    def register_plugin(self, info: PluginInfo) -> None:
        self.plugins[info.plugin_id] = info

    def enabled_tools(self, mode: str) -> list[BaseTool]:
        out = []
        for spec in self.tools.values():
            if spec.enabled and mode in spec.modes:
                if mode == "ask" and spec.name in {
                    "write_file",
                    "search_replace",
                    "run_command",
                    "delete_file",
                }:
                    continue
                out.append(spec.tool)
        return out


registry = PluginRegistry()
