from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import asyncssh

from code_agent.workspace.backend import get_workspace_backend
from code_agent.workspace.ssh_pool import ssh_pool

log = logging.getLogger(__name__)


@dataclass
class _Forward:
    listener: Any
    local_port: int


class SshPortForwarder:
    """Cache SSH local port forwards: remote 127.0.0.1:{port} → local ephemeral port."""

    def __init__(self) -> None:
        self._forwards: dict[tuple[str, int], _Forward] = {}
        self._lock = asyncio.Lock()

    async def local_port(self, workspace_id: str, remote_port: int) -> int:
        key = (workspace_id, int(remote_port))
        async with self._lock:
            existing = self._forwards.get(key)
            if existing is not None:
                return existing.local_port

            from code_agent.db.models import Workspace

            ws = await Workspace.get_or_none(id=workspace_id)
            if not ws:
                raise RuntimeError("workspace_not_found")
            backend = await get_workspace_backend(ws)
            conn = await backend._conn()  # type: ignore[attr-defined]
            # listen_port=0 → OS assigns
            listener = await conn.forward_local_port("127.0.0.1", 0, "127.0.0.1", int(remote_port))
            local = int(listener.get_port())
            self._forwards[key] = _Forward(listener=listener, local_port=local)
            log.info("ssh forward %s remote:%s -> local:%s", workspace_id, remote_port, local)
            return local

    async def drop_workspace(self, workspace_id: str) -> None:
        async with self._lock:
            keys = [k for k in self._forwards if k[0] == workspace_id]
            for key in keys:
                fwd = self._forwards.pop(key, None)
                if fwd is None:
                    continue
                try:
                    fwd.listener.close()
                except Exception:
                    pass


ssh_forwards = SshPortForwarder()
