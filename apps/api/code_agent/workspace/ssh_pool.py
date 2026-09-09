from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import asyncssh

from code_agent.config import settings
from code_agent.crypto import decrypt_secret, encrypt_secret


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
            try:
                # cheap liveness probe
                await asyncio.wait_for(conn.run("true", check=False), timeout=5)
                return conn
            except Exception:
                await self._drop_unlocked(key)

        kwargs: dict[str, Any] = {
            "host": auth.host,
            "port": auth.port,
            "username": auth.username,
            "login_timeout": int(settings.get("ssh.login_timeout") or 20),
        }
        known_hosts = settings.get("ssh.known_hosts")
        if known_hosts in (None, "", False, "null"):
            kwargs["known_hosts"] = None
        elif known_hosts is True or known_hosts == "auto":
            # Use default OpenSSH known_hosts files
            pass
        else:
            kwargs["known_hosts"] = str(known_hosts)
        keepalive = settings.get("ssh.keepalive_interval")
        if keepalive not in (None, "", False):
            kwargs["keepalive_interval"] = int(keepalive)
        if auth.private_key:
            kwargs["client_keys"] = [
                asyncssh.import_private_key(auth.private_key, passphrase=auth.passphrase)
            ]
        if auth.password:
            kwargs["password"] = auth.password
        if not auth.private_key and not auth.password:
            # try agent / default keys
            kwargs["agent_forwarding"] = False

        conn = await asyncssh.connect(**kwargs)
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
