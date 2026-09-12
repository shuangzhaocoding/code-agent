from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_agent.config import settings

USER_MCP_REL = Path(".code-agent") / "mcp.json"
WORKSPACE_MCP_REL = ".code-agent/mcp.json"

PRESETS: list[dict[str, Any]] = [
    {
        "id": "postgres",
        "title": "PostgreSQL",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost:5432/db"],
        "hint": "把连接串换成你的数据库。只读查询也走 MCP 工具。",
    },
    {
        "id": "figma",
        "title": "Figma",
        "transport": "http",
        "url": "https://mcp.figma.com/mcp",
        "hint": "在 headers 里放 Figma 访问令牌，例如 Authorization: Bearer …",
    },
    {
        "id": "browser",
        "title": "浏览器 (Playwright)",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "hint": "本地拉起 Playwright MCP，给 Agent 打开页面、点选、截图。",
    },
    {
        "id": "http-api",
        "title": "内部 HTTP API",
        "transport": "http",
        "url": "http://127.0.0.1:3100/mcp",
        "hint": "指向你们自己的 MCP HTTP 端点（JSON-RPC）。",
    },
]


def user_mcp_path() -> Path:
    raw = settings.get("paths.user_config") or "~/.code-agent/config.yaml"
    return Path(raw).expanduser().parent / "mcp.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _servers_from_doc(doc: dict[str, Any], origin: str) -> dict[str, dict[str, Any]]:
    raw = doc.get("mcpServers") if isinstance(doc.get("mcpServers"), dict) else doc
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        item = dict(spec)
        item["name"] = str(name).strip()
        item["origin"] = origin
        item.setdefault("enabled", True)
        item.setdefault("transport", "http" if item.get("url") else "stdio")
        if item["name"]:
            out[item["name"]] = item
    return out


def load_mcp_servers(workspace_root: str | None = None) -> list[dict[str, Any]]:
    merged = _servers_from_doc(_read_json(user_mcp_path()), "user")
    if workspace_root:
        ws_doc = _read_json(Path(workspace_root) / WORKSPACE_MCP_REL)
        merged.update(_servers_from_doc(ws_doc, "workspace"))
    return list(merged.values())


def _dump_servers(servers: list[dict[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for item in servers:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        spec = {
            k: v
            for k, v in item.items()
            if k not in {"name", "origin", "tools", "error", "status"} and v not in (None, "", [])
        }
        body[name] = spec
    return {"mcpServers": body}


def save_mcp_servers(servers: list[dict[str, Any]], *, workspace_root: str | None, origin: str) -> None:
    if origin == "workspace":
        if not workspace_root:
            raise ValueError("workspace_root required")
        path = Path(workspace_root) / WORKSPACE_MCP_REL
    else:
        path = user_mcp_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_mcp_servers(workspace_root)
    by_name = {s["name"]: s for s in existing if s.get("origin") == origin}
    incoming = {s["name"]: {**s, "origin": origin} for s in servers}
    by_name.update(incoming)
    # deletions: if a name is missing from incoming list when replacing full set
    keep = {s["name"] for s in servers}
    by_name = {k: v for k, v in by_name.items() if k in keep}
    path.write_text(json.dumps(_dump_servers(list(by_name.values())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert_mcp_server(spec: dict[str, Any], *, workspace_root: str | None) -> dict[str, Any]:
    origin = str(spec.get("origin") or "workspace")
    if origin not in {"user", "workspace"}:
        origin = "workspace"
    name = str(spec.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    current = [s for s in load_mcp_servers(workspace_root) if s.get("origin") == origin]
    others = [s for s in current if s.get("name") != name]
    item = {**spec, "name": name, "origin": origin}
    others.append(item)
    save_mcp_servers(others, workspace_root=workspace_root, origin=origin)
    return item


def delete_mcp_server(name: str, *, workspace_root: str | None, origin: str) -> None:
    current = [s for s in load_mcp_servers(workspace_root) if s.get("origin") == origin and s.get("name") != name]
    save_mcp_servers(current, workspace_root=workspace_root, origin=origin)


def sanitize_tool_name(server: str, tool: str) -> str:
    def _clean(value: str) -> str:
        chars = [c if c.isalnum() else "_" for c in value]
        text = "".join(chars).strip("_")
        return text or "tool"

    name = f"mcp_{_clean(server)}_{_clean(tool)}"
    return name[:64]
