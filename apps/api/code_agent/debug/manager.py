"""In-memory Python debug session registry."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from code_agent.debug.launch import (
    LaunchConfig,
    default_current_file_config,
    expand_config,
    load_launch_configs_from_text,
    parse_launch_entry,
)
from code_agent.debug.session import DebugSession
from code_agent.db.models import Workspace
from code_agent.workspace.backend import get_workspace_backend


class DebugManager:
    def __init__(self) -> None:
        self._sessions: dict[str, DebugSession] = {}
        self._subs: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    def get(self, session_id: str) -> DebugSession | None:
        return self._sessions.get(session_id)

    def list_for_workspace(self, workspace_id: str) -> list[DebugSession]:
        return [s for s in self._sessions.values() if str(s.workspace.id) == workspace_id]

    async def subscribe(self, session_id: str, ws: WebSocket) -> None:
        self._subs.setdefault(session_id, []).append(ws)

    async def unsubscribe(self, session_id: str, ws: WebSocket) -> None:
        rows = self._subs.get(session_id) or []
        if ws in rows:
            rows.remove(ws)
        if not rows:
            self._subs.pop(session_id, None)

    async def _broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._subs.get(session_id) or []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unsubscribe(session_id, ws)

    async def load_configs(self, workspace: Workspace) -> list[dict[str, Any]]:
        backend = await get_workspace_backend(workspace)
        texts: list[str] = []
        for rel in (".code-agent/launch.json", ".vscode/launch.json"):
            try:
                texts.append(await backend.read_text(rel))
            except Exception:
                continue
        await backend.close()
        configs: list[LaunchConfig] = []
        for text in texts:
            configs.extend(load_launch_configs_from_text(text))
        # de-dupe by name
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for cfg in configs:
            if cfg.name in seen:
                continue
            seen.add(cfg.name)
            out.append(
                {
                    "name": cfg.name,
                    "request": cfg.request,
                    "program": cfg.program,
                    "module": cfg.module,
                    "cwd": cfg.cwd,
                    "args": cfg.args,
                    "env": cfg.env,
                    "python": cfg.python,
                    "stopOnEntry": cfg.stop_on_entry,
                    "justMyCode": cfg.just_my_code,
                }
            )
        return out

    async def start(
        self,
        workspace: Workspace,
        *,
        program: str | None = None,
        module: str | None = None,
        cwd: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        python: str | None = None,
        stop_on_entry: bool | None = None,
        just_my_code: bool = True,
        config_name: str | None = None,
        config: dict[str, Any] | None = None,
        breakpoints: dict[str, list[dict[str, Any]]] | None = None,
        exception_filters: list[str] | None = None,
        current_file: str | None = None,
    ) -> DebugSession:
        async with self._lock:
            base: LaunchConfig | None = None
            if config:
                base = parse_launch_entry(config)
            elif config_name:
                for row in await self.load_configs(workspace):
                    if row.get("name") == config_name:
                        base = parse_launch_entry(row)
                        break
            if base is None:
                if module:
                    base = LaunchConfig(name="Python: Module", module=module, cwd=cwd or ".")
                elif program:
                    base = default_current_file_config(program)
                elif current_file:
                    base = default_current_file_config(current_file)
                else:
                    raise ValueError("Need program, module, current_file, or launch config")

            if program:
                base.program = program
                base.module = None
            if module:
                base.module = module
                base.program = None
            if cwd is not None:
                base.cwd = cwd
            if args is not None:
                base.args = list(args)
            if env is not None:
                base.env = dict(env)
            if python:
                base.python = python
            if stop_on_entry is not None:
                base.stop_on_entry = stop_on_entry
            base.just_my_code = just_my_code

            cfg = expand_config(
                base,
                workspace_root=str(workspace.root_path),
                current_file=current_file or program,
            )

            session = DebugSession(
                workspace=workspace,
                config=cfg,
                breakpoints=breakpoints or {},
                exception_filters=exception_filters,
            )

            session_id = session.id

            async def broadcast(msg: dict[str, Any]) -> None:
                await self._broadcast(session_id, msg)
                payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
                typ = msg.get("type")
                state = payload.get("state") if isinstance(payload, dict) else None
                if typ in {"exited", "terminated"} or (
                    typ == "session" and state in {"terminated", "stopped"}
                ):
                    # Process ended; drop from registry (stop may already have cleaned resources).
                    self._sessions.pop(session_id, None)

            session.broadcast = broadcast
            self._sessions[session.id] = session

        async def _boot(sess: DebugSession) -> None:
            try:
                await sess.start()
            except Exception:
                # sess.start already emitted error + cleaned subprocess; drop registry entry.
                self._sessions.pop(sess.id, None)
                subs = self._subs.pop(sess.id, None) or []
                for ws in subs:
                    try:
                        await ws.close()
                    except Exception:
                        pass

        asyncio.create_task(_boot(session))
        return session

    async def stop(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if not session:
            return
        await session.stop()
        for ws in list(self._subs.get(session_id) or []):
            try:
                await ws.close()
            except Exception:
                pass
        self._subs.pop(session_id, None)

    def discard(self, session_id: str) -> None:
        """Remove a finished session from the registry without stopping again."""
        self._sessions.pop(session_id, None)
        self._subs.pop(session_id, None)


debug_manager = DebugManager()
