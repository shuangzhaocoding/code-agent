from __future__ import annotations

from pathlib import Path

from code_agent.mcp.config import delete_mcp_server, load_mcp_servers, sanitize_tool_name, upsert_mcp_server


def test_sanitize_tool_name():
    assert sanitize_tool_name("pg!", "query-rows") == "mcp_pg_query_rows"
    assert len(sanitize_tool_name("x" * 80, "y" * 80)) <= 64


def test_upsert_and_load_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("code_agent.mcp.config.user_mcp_path", lambda: tmp_path / "user-mcp.json")
    root = str(tmp_path / "ws")
    Path(root).mkdir()
    item = upsert_mcp_server(
        {
            "name": "browser",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
            "origin": "workspace",
        },
        workspace_root=root,
    )
    assert item["name"] == "browser"
    servers = load_mcp_servers(root)
    assert [s["name"] for s in servers] == ["browser"]
    upsert_mcp_server(
        {"name": "figma", "transport": "http", "url": "https://mcp.figma.com/mcp", "origin": "user"},
        workspace_root=root,
    )
    names = {s["name"] for s in load_mcp_servers(root)}
    assert names == {"browser", "figma"}
    delete_mcp_server("browser", workspace_root=root, origin="workspace")
    names = {s["name"] for s in load_mcp_servers(root)}
    assert names == {"figma"}
