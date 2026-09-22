from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncssh

from code_agent.config import settings
from code_agent.crypto import decrypt_secret, encrypt_secret

_DEFAULT_KNOWN_HOSTS = ("~/.ssh/known_hosts", "~/.ssh/known_hosts2")


def _read_utf8(path: str) -> str | None:
    try:
        return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _known_hosts_arg(value: Any) -> bytes | None:
    """Load known_hosts as UTF-8 bytes so Windows GBK locale cannot decode the file."""
    if value in (None, "", False, "null"):
        return None
    paths: tuple[str, ...]
    if value is True or value == "auto":
        paths = _DEFAULT_KNOWN_HOSTS
    else:
        paths = (str(value),)
    blobs = [text for rel in paths if (text := _read_utf8(rel))]
    return "\n".join(blobs).encode("utf-8") if blobs else None


def connect_kwargs(auth: SshAuth) -> dict[str, Any]:
    """asyncssh.connect kwargs that stay encoding-safe on Windows (GBK locale).

    asyncssh opens ``~/.ssh/config`` and known_hosts in text mode without an
    encoding, so a UTF-8 comment/path raises::

        UnicodeDecodeError: 'gbk' codec can't decode byte 0xac ...
    """
    kwargs: dict[str, Any] = {
        "host": auth.host,
        "port": auth.port,
        "username": auth.username,
        "login_timeout": int(settings.get("ssh.login_timeout") or 20),
        "encoding": "utf-8",
        "errors": "replace",
        # Do not parse OpenSSH config: `open(path)` uses locale encoding.
        "config": None,
        "known_hosts": _known_hosts_arg(settings.get("ssh.known_hosts")),
        # Keep the session alive across long UI idle (NAT / server ClientAlive).
        "tcp_keepalive": True,
    }
    cfg = settings.get("ssh.config")
    if cfg not in (None, "", False, "null"):
        kwargs["config"] = str(cfg)
    keepalive = settings.get("ssh.keepalive_interval")
    if keepalive in (None, "", False):
        keepalive = 30
    kwargs["keepalive_interval"] = int(keepalive)
    count_max = settings.get("ssh.keepalive_count_max")
    if count_max in (None, "", False):
        count_max = 10
    kwargs["keepalive_count_max"] = int(count_max)
    if auth.private_key:
        kwargs["client_keys"] = [
            asyncssh.import_private_key(auth.private_key, passphrase=auth.passphrase)
        ]
        kwargs["agent_path"] = None
    elif auth.password:
        # None (not []) disables default ~/.ssh/id_* and ssh-agent.
        kwargs["client_keys"] = None
        kwargs["agent_path"] = None
    else:
        kwargs["agent_forwarding"] = False
    if auth.password:
        kwargs["password"] = auth.password
    return kwargs


def _conn_is_dead(conn: asyncssh.SSHClientConnection) -> bool:
    try:
        if conn.is_closing():
            return True
    except Exception:
        return True
    return False


@dataclass
class SshAuth:
    host: str
    port: int
    username: str
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None

    def fingerprint(self) -> str:
        return f"{self.username}@{self.host}:{self.port}"

    def to_secret_blob(self) -> str:
        payload = {
            "password": self.password or "",
            "private_key": self.private_key or "",
            "passphrase": self.passphrase or "",
        }
        return encrypt_secret(json.dumps(payload))

    @classmethod
    def from_workspace_fields(
        cls,
        *,
        host: str,
        port: int,
        username: str,
        secret_blob: str,
    ) -> SshAuth:
        raw = decrypt_secret(secret_blob or "") or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        return cls(
            host=host,
            port=int(port or 22),
            username=username,
            password=(data.get("password") or None) or None,
            private_key=(data.get("private_key") or None) or None,
            passphrase=(data.get("passphrase") or None) or None,
        )


class SshPool:
    """Process-local asyncssh connection pool keyed by workspace id or auth fingerprint."""

    def __init__(self) -> None:
        self._conns: dict[str, asyncssh.SSHClientConnection] = {}
        self._sftps: dict[str, asyncssh.SFTPClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def connect(self, key: str, auth: SshAuth) -> asyncssh.SSHClientConnection:
        async with self._lock(key):
            return await self._connect_unlocked(key, auth)

    async def _connect_unlocked(self, key: str, auth: SshAuth) -> asyncssh.SSHClientConnection:
        conn = self._conns.get(key)
        if conn is not None:
            if _conn_is_dead(conn):
                await self._drop_unlocked(key)
            else:
                try:
                    # cheap liveness probe — recovers after overnight sleep / NAT drop
                    await asyncio.wait_for(conn.run("true", check=False), timeout=5)
                    return conn
                except Exception:
                    await self._drop_unlocked(key)

        conn = await asyncssh.connect(**connect_kwargs(auth))
        self._conns[key] = conn
        return conn

    async def sftp(self, key: str, auth: SshAuth) -> asyncssh.SFTPClient:
        async with self._lock(key):
            conn = await self._connect_unlocked(key, auth)
            existing = self._sftps.get(key)
            if existing is not None:
                return existing
            client = await conn.start_sftp_client()
            self._sftps[key] = client
            return client

    async def _drop_unlocked(self, key: str) -> None:
        sftp = self._sftps.pop(key, None)
        if sftp is not None:
            try:
                sftp.exit()
            except Exception:
                try:
                    sftp.close()
                except Exception:
                    pass
        conn = self._conns.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    async def drop(self, key: str) -> None:
        async with self._lock(key):
            await self._drop_unlocked(key)


ssh_pool = SshPool()
