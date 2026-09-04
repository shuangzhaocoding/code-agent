from __future__ import annotations

import textwrap
from pathlib import Path

from unittest.mock import AsyncMock, patch

import pytest

from code_agent.plugins.base import PluginInfo, registry
from code_agent.plugins.loader import (
    activate_workspace_plugins,
    active_workspace_root,
    load_workspace_plugins,
    unload_workspace_plugins,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    unload_workspace_plugins()
    yield
    unload_workspace_plugins()


def _write_plugin(plugins_dir: Path, plugin_id: str, tool_name: str) -> None:
    plugins_dir.mkdir(parents=True, exist_ok=True)
    code = textwrap.dedent(
        f"""
        def register(registry):
            from langchain_core.tools import tool

            @tool
            async def {tool_name}() -> str:
                \"\"\"Workspace plugin tool.\"\"\"
                return "ok"

            registry.register_tool({tool_name}, source="plugin:{plugin_id}", modes=("agent",))
        """
    )
    (plugins_dir / f"{plugin_id}.py").write_text(code, encoding="utf-8")


@pytest.mark.asyncio
async def test_load_workspace_plugins(tmp_path: Path):
    ws = tmp_path / "project"
    ws.mkdir()
    _write_plugin(ws / ".code-agent" / "plugins", "ws_tool", "ws_hello")

    loaded = load_workspace_plugins(str(ws))
    assert loaded == ["ws_tool"]
    assert "ws_hello" in registry.tools
    info = registry.plugins["ws_tool"]
    assert info.origin == "workspace"


@pytest.mark.asyncio
async def test_workspace_plugin_does_not_override_repo_id(tmp_path: Path):
    registry.register_plugin(
        PluginInfo(
            plugin_id="git",
            source="builtin",
            title="Git",
            origin="repo",
        )
    )
    ws = tmp_path / "project"
    ws.mkdir()
    _write_plugin(ws / ".code-agent" / "plugins", "git", "ws_git")

    loaded = load_workspace_plugins(str(ws))
    assert loaded == []
    assert "ws_git" not in registry.tools


def test_unload_workspace_plugins(tmp_path: Path):
    ws = tmp_path / "project"
    ws.mkdir()
    _write_plugin(ws / ".code-agent" / "plugins", "ws_tool", "ws_hello")
    load_workspace_plugins(str(ws))

    removed = unload_workspace_plugins()
    assert removed == ["ws_tool"]
    assert "ws_tool" not in registry.plugins
    assert "ws_hello" not in registry.tools


@pytest.mark.asyncio
async def test_activate_workspace_plugins_switches_workspace(tmp_path: Path):
    ws_a = tmp_path / "a"
    ws_b = tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    _write_plugin(ws_a / ".code-agent" / "plugins", "plugin_a", "tool_a")
    _write_plugin(ws_b / ".code-agent" / "plugins", "plugin_b", "tool_b")

    with patch("code_agent.plugins.loader.apply_plugin_states", AsyncMock()):
        result_a = await activate_workspace_plugins(str(ws_a))
        assert "plugin_a" in result_a["loaded"]
        assert "tool_a" in registry.tools
        assert active_workspace_root() == str(ws_a.resolve())

        result_b = await activate_workspace_plugins(str(ws_b))
        assert result_a["loaded"][0] in result_b["removed"]
        assert "plugin_a" not in registry.plugins
        assert "tool_b" in registry.tools
        assert active_workspace_root() == str(ws_b.resolve())
