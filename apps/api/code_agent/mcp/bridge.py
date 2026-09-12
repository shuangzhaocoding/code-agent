from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from code_agent.mcp.config import load_mcp_servers, sanitize_tool_name
from code_agent.mcp.protocol import McpError, McpSession, open_session
from code_agent.plugins.base import PluginInfo, registry

_sessions: dict[str, McpSession] = {}
_server_status: dict[str, dict[str, Any]] = {}
_MCP_PLUGIN = "builtin.mcp"


def register_mcp_plugin() -> None:
    registry.register_plugin(
        PluginInfo(
            plugin_id=_MCP_PLUGIN,
            source="builtin",
            title="MCP 客户端",
            description="连接自备 MCP 服务器（数据库、Figma、浏览器、内部 API）。不做应用市场。",
            kind="tools",
            origin="builtin",
            contributes=("tools",),
            author="Code Agent",
            icon="globe",
            accent="#0891b2",
            keywords=("mcp", "postgres", "figma", "browser", "api"),
        )
    )


def _schema_model(server: str, spec: dict[str, Any]) -> type[BaseModel]:
    props = ((spec.get("inputSchema") or {}) if isinstance(spec.get("inputSchema"), dict) else {}).get("properties") or {}
    required = set(((spec.get("inputSchema") or {}) if isinstance(spec.get("inputSchema"), dict) else {}).get("required") or [])
    fields: dict[str, Any] = {}
    for key, meta in props.items() if isinstance(props, dict) else []:
        name = re.sub(r"[^a-zA-Z0-9_]", "_", str(key)) or "arg"
        desc = ""
        if isinstance(meta, dict):
            desc = str(meta.get("description") or "")
        default = ... if key in required else None
        fields[name] = (str, Field(default, description=desc))
    model_name = f"McpArgs_{sanitize_tool_name(server, spec.get('name') or 'tool')}"
    if not fields:
        return create_model(model_name, payload=(str, Field("", description="JSON payload")))
    return create_model(model_name, **fields)


async def _ensure_session(spec: dict[str, Any]) -> McpSession:
    name = str(spec.get("name") or "")
    session = _sessions.get(name)
    if session:
        return session
    session = open_session(spec)
    await session.start()
    _sessions[name] = session
    return session


def _unregister_mcp_tools() -> None:
    drop = [key for key, spec in registry.tools.items() if spec.source == "mcp" or spec.plugin_id == _MCP_PLUGIN]
    for key in drop:
        registry.tools.pop(key, None)


def mcp_server_views(workspace_root: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in load_mcp_servers(workspace_root):
        extra = _server_status.get(str(spec.get("name") or "")) or {}
        out.append(
            {
                **spec,
                "status": extra.get("status") or ("disabled" if spec.get("enabled") is False else "idle"),
                "error": extra.get("error") or "",
                "tools": extra.get("tools") or [],
            }
        )
    return out


async def forget_mcp_session(name: str) -> None:
    session = _sessions.pop(name, None)
    _server_status.pop(name, None)
    if session:
        try:
            await session.close()
        except Exception:
            pass


async def refresh_mcp_tools(workspace_root: str | None, *, persist_sessions: bool = False) -> list[dict[str, Any]]:
    await shutdown_mcp_sessions()
    _unregister_mcp_tools()
    registry.loading_plugin_id = _MCP_PLUGIN
    register_mcp_plugin()
    summaries: list[dict[str, Any]] = []
    live_names: set[str] = set()
    for spec in load_mcp_servers(workspace_root):
        name = str(spec.get("name") or "")
        live_names.add(name)
        if spec.get("enabled") is False:
            summary = {**spec, "status": "disabled", "tools": [], "error": ""}
            summaries.append(summary)
            _server_status[name] = summary
            continue
        try:
            session = await _ensure_session(spec)
            tools = await session.list_tools()
        except Exception as exc:
            summary = {**spec, "status": "error", "error": str(exc)[:400], "tools": []}
            summaries.append(summary)
            _server_status[name] = summary
            continue
        registered: list[dict[str, Any]] = []
        for tool_spec in tools:
            if not isinstance(tool_spec, dict):
                continue
            remote_name = str(tool_spec.get("name") or "").strip()
            if not remote_name:
                continue
            tool_name = sanitize_tool_name(spec["name"], remote_name)
            description = str(tool_spec.get("description") or remote_name)
            ArgsModel = _schema_model(spec["name"], tool_spec)

            async def _run(*, _server=spec, _remote=remote_name, **kwargs: Any) -> str:
                live = await _ensure_session(_server)
                payload = {k: v for k, v in kwargs.items() if v is not None and k != "payload"}
                if "payload" in kwargs and kwargs["payload"] and not payload:
                    import json

                    try:
                        parsed = json.loads(str(kwargs["payload"]))
                        if isinstance(parsed, dict):
                            payload = parsed
                    except Exception:
                        payload = {"input": kwargs["payload"]}
                return await live.call_tool(_remote, payload)

            registry.register_tool(
                StructuredTool.from_function(
                    coroutine=_run,
                    name=tool_name,
                    description=f"[MCP:{spec['name']}] {description}",
                    args_schema=ArgsModel,
                ),
                source="mcp",
                modes=("ask", "agent", "plan"),
                plugin_id=_MCP_PLUGIN,
            )
            registered.append({"name": tool_name, "remote": remote_name, "description": description})
        summary = {**spec, "status": "ok", "tools": registered, "error": ""}
        summaries.append(summary)
        _server_status[name] = summary
    for stale in [key for key in _server_status if key not in live_names]:
        _server_status.pop(stale, None)
    registry.loading_plugin_id = ""
    if not persist_sessions:
        await shutdown_mcp_sessions()
    return summaries


async def shutdown_mcp_sessions() -> None:
    sessions = list(_sessions.values())
    _sessions.clear()
    for session in sessions:
        try:
            await session.close()
        except Exception:
            pass


async def probe_mcp_server(spec: dict[str, Any]) -> dict[str, Any]:
    session = open_session(spec)
    try:
        await session.start()
        tools = await session.list_tools()
        return {"ok": True, "tools": tools, "error": ""}
    except McpError as exc:
        return {"ok": False, "tools": [], "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "tools": [], "error": str(exc)[:400]}
    finally:
        await session.close()
