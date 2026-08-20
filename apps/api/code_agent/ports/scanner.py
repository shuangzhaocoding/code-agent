from __future__ import annotations

import socket
from pathlib import Path


_LISTEN = "0A"


def _parse_ipv4(hex_addr: str) -> str:
    raw = bytes.fromhex(hex_addr)
    return ".".join(str(b) for b in reversed(raw))


def _parse_ipv6(hex_addr: str) -> str:
    raw = bytearray.fromhex(hex_addr)
    for i in range(0, 16, 4):
        raw[i : i + 4] = raw[i : i + 4][::-1]
    try:
        return socket.inet_ntop(socket.AF_INET6, bytes(raw))
    except OSError:
        return "::"


def _read_tcp_table(path: Path, ipv6: bool) -> list[tuple[str, int, int]]:
    if not path.exists():
        return []
    rows: list[tuple[str, int, int]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        if parts[3].upper() != _LISTEN:
            continue
        local = parts[1]
        try:
            addr_hex, port_hex = local.split(":")
            port = int(port_hex, 16)
            inode = int(parts[9])
        except ValueError:
            continue
        host = _parse_ipv6(addr_hex) if ipv6 else _parse_ipv4(addr_hex)
        rows.append((host, port, inode))
    return rows


def _inode_owners() -> dict[int, tuple[int, str]]:
    owners: dict[int, tuple[int, str]] = {}
    proc = Path("/proc")
    if not proc.exists():
        return owners
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except (PermissionError, FileNotFoundError, OSError):
            continue
        cmdline = ""
        try:
            raw = (entry / "cmdline").read_bytes()
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        except OSError:
            pass
        if not cmdline:
            try:
                cmdline = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                cmdline = f"pid:{pid}"
        for fd in fds:
            try:
                target = str(fd.readlink())
            except OSError:
                continue
            if not target.startswith("socket:["):
                continue
            try:
                inode = int(target[8:-1])
            except ValueError:
                continue
            owners.setdefault(inode, (pid, cmdline[:160]))
    return owners


def _is_local_bind(host: str) -> bool:
    h = host.lower()
    if h in {"0.0.0.0", "::", "::0", "*"}:
        return True
    if h.startswith("127.") or h == "localhost":
        return True
    if h in {"::1", "0:0:0:0:0:0:0:1"} or h.endswith("::1"):
        return True
    return False


def _is_ipv6_only_loopback(host: str) -> bool:
    h = host.lower()
    return h in {"::1", "0:0:0:0:0:0:0:1"} or (":" in h and h.endswith("::1"))


def _display_name(cmdline: str) -> str:
    if not cmdline:
        return "unknown"
    parts = cmdline.split()
    if not parts:
        return "unknown"
    base = Path(parts[0]).name
    if base in {"node", "nodejs", "python", "python3", "uv", "npm", "pnpm", "yarn", "bun"} and len(parts) > 1:
        next_tok = Path(parts[1]).name
        if next_tok and not next_tok.startswith("-"):
            return f"{base} {next_tok}"
    return base


def _probe_tcp(host: str, port: int, timeout: float = 0.35) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            return True
    except OSError:
        return False


def choose_connect_host(port: int, address: str) -> str:
    addresses = [part.strip() for part in str(address).split(",") if part.strip()]
    ipv6_only = bool(addresses) and all(_is_ipv6_only_loopback(a) for a in addresses)
    if ipv6_only:
        return "::1"
    if _probe_tcp("127.0.0.1", port):
        return "127.0.0.1"
    if _probe_tcp("::1", port):
        return "::1"
    if any(_is_ipv6_only_loopback(a) for a in addresses):
        return "::1"
    return "127.0.0.1"


def format_open_url(connect_host: str, port: int) -> str:
    if ":" in connect_host:
        return f"http://[{connect_host}]:{port}"
    return f"http://{connect_host}:{port}"


def list_listening_ports(*, exclude_ports: set[int] | None = None) -> list[dict]:
    """Return localhost-reachable TCP listeners on this host."""
    exclude = exclude_ports or set()
    owners = _inode_owners()
    by_port: dict[int, dict] = {}

    for host, port, inode in (
        *_read_tcp_table(Path("/proc/net/tcp"), False),
        *_read_tcp_table(Path("/proc/net/tcp6"), True),
    ):
        if port in exclude or not _is_local_bind(host):
            continue
        pid, cmdline = owners.get(inode, (None, ""))
        candidate = {
            "port": port,
            "address": host,
            "pid": pid,
            "process": _display_name(cmdline) if cmdline else None,
            "cmdline": cmdline or None,
        }
        existing = by_port.get(port)
        if not existing:
            by_port[port] = candidate
            continue
        prefer = False
        if existing["address"] in {"0.0.0.0", "::", "::0"} and (
            host.startswith("127.") or _is_ipv6_only_loopback(host)
        ):
            prefer = True
        if not existing.get("process") and candidate.get("process"):
            prefer = True
        if prefer:
            # Keep both addresses when merging
            old_addr = existing["address"]
            by_port[port] = candidate
            if old_addr != host:
                by_port[port]["address"] = f"{old_addr}, {host}"
        elif host not in {a.strip() for a in existing["address"].split(",")}:
            existing["address"] = f"{existing['address']}, {host}"

    items: list[dict] = []
    for port, row in by_port.items():
        connect_host = choose_connect_host(port, row["address"])
        row["connect_host"] = connect_host
        row["url"] = format_open_url(connect_host, port)
        row["preview_path"] = f"/api/preview/{port}/"
        row["reachable"] = _probe_tcp(connect_host, port)
        items.append(row)

    items.sort(key=lambda row: row["port"])
    return items


def get_port_entry(port: int) -> dict | None:
    for item in list_listening_ports():
        if item["port"] == port:
            return item
    return None


def is_port_listening(port: int) -> bool:
    return get_port_entry(port) is not None


def kill_port_process(port: int, *, allow_self: bool = False) -> dict:
    """Terminate the process listening on ``port``. Returns status details."""
    import os
    import signal
    import time

    entry = get_port_entry(port)
    if not entry:
        raise ValueError("port_not_listening")

    pid = entry.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        raise ValueError("pid_unknown")

    our_pid = os.getpid()
    if pid in {our_pid, os.getppid()}:
        raise ValueError("pid_self")

    # Protect common system daemons unless explicitly allowed later
    if port in {22, 25, 53, 111, 123, 631} and not allow_self:
        raise ValueError("port_protected")

    try:
        os.kill(pid, 0)
    except ProcessLookupError as exc:
        raise ValueError("pid_gone") from exc
    except PermissionError as exc:
        raise ValueError("permission_denied") from exc

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"ok": True, "port": port, "pid": pid, "signal": "none", "process": entry.get("process")}
    except PermissionError as exc:
        raise ValueError("permission_denied") from exc

    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return {
                "ok": True,
                "port": port,
                "pid": pid,
                "signal": "SIGTERM",
                "process": entry.get("process"),
            }
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return {
            "ok": True,
            "port": port,
            "pid": pid,
            "signal": "SIGTERM",
            "process": entry.get("process"),
        }
    except PermissionError as exc:
        raise ValueError("permission_denied") from exc

    return {
        "ok": True,
        "port": port,
        "pid": pid,
        "signal": "SIGKILL",
        "process": entry.get("process"),
    }
