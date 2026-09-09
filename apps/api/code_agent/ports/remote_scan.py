from __future__ import annotations

import re
from typing import Any

from code_agent.ports.scanner import format_open_url
from code_agent.workspace.backend import WorkspaceBackend

_SS_LINE = re.compile(
    r"^(?:LISTEN|UNCONN)\s+\d+\s+\d+\s+(\S+):(\d+)\s+\S+",
    re.IGNORECASE,
)
_SS_FALLBACK = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}|\[?[0-9a-fA-F:]+\]?|\*):(\d+)\s")


def _is_local_bind(host: str) -> bool:
    h = (host or "").strip("[]").lower()
    if h in {"0.0.0.0", "*", "::", "::0", "127.0.0.1", "localhost", "::1"}:
        return True
    if h.startswith("127."):
        return True
    return False


def parse_ss_listening(stdout: str, *, exclude_ports: set[int] | None = None) -> list[dict[str, Any]]:
    """Parse `ss -lnt` / `ss -lntH` output into port entries."""
    exclude = exclude_ports or set()
    by_port: dict[int, dict[str, Any]] = {}
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("state") or line.lower().startswith("netid"):
            continue
        m = _SS_LINE.match(line) or _SS_FALLBACK.search(line)
        if not m:
            continue
        host = m.group(1).strip("[]")
        try:
            port = int(m.group(2))
        except ValueError:
            continue
        if port in exclude or port < 1 or port > 65535:
            continue
        if not _is_local_bind(host):
            continue
        existing = by_port.get(port)
        if not existing:
            by_port[port] = {
                "port": port,
                "address": host,
                "pid": None,
                "process": None,
                "cmdline": None,
            }
        elif host not in {a.strip() for a in existing["address"].split(",")}:
            existing["address"] = f"{existing['address']}, {host}"

    items: list[dict[str, Any]] = []
    for port, row in sorted(by_port.items(), key=lambda kv: kv[0]):
        row["connect_host"] = "127.0.0.1"
        row["url"] = format_open_url("127.0.0.1", port)
        row["preview_path"] = f"/api/preview/{port}/"
        row["reachable"] = True
        row["remote"] = True
        items.append(row)
    return items


async def list_remote_listening_ports(
    backend: WorkspaceBackend,
    *,
    exclude_ports: set[int] | None = None,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    """Discover listening TCP ports on a remote workspace host via `ss`."""
    code, out, err = await backend.run_command("ss -lntH 2>/dev/null || ss -lnt", cwd=".", timeout=15)
    if code not in {0, 1}:
        # fallback: empty rather than hard-fail the panel
        return []
    items = parse_ss_listening(out or err or "", exclude_ports=exclude_ports)
    if workspace_id:
        for item in items:
            item["workspace_id"] = workspace_id
            item["preview_path"] = f"/api/preview/{item['port']}/?workspace_id={workspace_id}"
            item["url"] = item["preview_path"]
    return items
