from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from code_agent.config import settings
from code_agent.db.models import TerminalSession, Workspace


class PtyHandle:
    def __init__(self, session_id: str, cwd: str, shell: str) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.shell = shell
        self.pid: int | None = None
        self.fd: int | None = None
        self.buffer = bytearray()
        self.max_buf = int(settings.get("terminal.scrollback_bytes") or 204800)
        self.subscribers: list[WebSocket] = []
        self.alive = False

    def spawn(self, cols: int, rows: int) -> None:
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.cwd)
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["CLICOLOR"] = "1"
            env["CLICOLOR_FORCE"] = "1"
            env["FORCE_COLOR"] = "1"
            os.execvpe(self.shell, [self.shell, "-il"], env)
        self.pid = pid
        self.fd = fd
        self.alive = True
        self.resize(cols, rows)
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        loop = asyncio.get_running_loop()
        loop.add_reader(fd, self._on_data)

    def resize(self, cols: int, rows: int) -> None:
        if self.fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

    def write(self, data: bytes) -> None:
        if self.fd is None:
            return
        os.write(self.fd, data)

    def _on_data(self) -> None:
        if self.fd is None:
            return
        try:
            chunk = os.read(self.fd, 4096)
        except OSError:
            chunk = b""
        if not chunk:
            asyncio.get_running_loop().remove_reader(self.fd)
            self.alive = False
            asyncio.create_task(self._broadcast_exit())
            return
        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_buf:
            self.buffer = self.buffer[-self.max_buf :]
        asyncio.create_task(self._broadcast(chunk))

    async def _broadcast(self, chunk: bytes) -> None:
        dead = []
        for ws in self.subscribers:
            try:
                await ws.send_bytes(chunk)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.subscribers:
                self.subscribers.remove(ws)

    async def _broadcast_exit(self) -> None:
        for ws in list(self.subscribers):
            try:
                await ws.send_json({"type": "exit"})
            except Exception:
                pass
        self.subscribers.clear()

    def close(self) -> None:
        if self.fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self.fd)
            except Exception:
                pass
            try:
                os.close(self.fd)
            except OSError:
                pass
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGHUP)
            except OSError:
                pass
        self.alive = False


class PtyManager:
    def __init__(self) -> None:
        self._sessions: dict[str, PtyHandle] = {}

    def get(self, session_id: str) -> PtyHandle | None:
        return self._sessions.get(session_id)

    def attach(self, session_id: str, cwd: str, cols: int, rows: int) -> PtyHandle:
        handle = self._sessions.get(session_id)
        if handle and handle.alive:
            return handle
        shell = settings.get("terminal.shell") or "/bin/bash"
        handle = PtyHandle(session_id, cwd, shell)
        handle.spawn(cols, rows)
        self._sessions[session_id] = handle
        return handle

    def drop(self, session_id: str) -> None:
        handle = self._sessions.pop(session_id, None)
        if handle:
            handle.close()


pty_manager = PtyManager()


async def create_terminal(workspace_id: str, title: str | None = None) -> TerminalSession:
    ws = await Workspace.get(id=workspace_id)
    cols = int(settings.get("terminal.default_cols") or 120)
    rows = int(settings.get("terminal.default_rows") or 32)
    row = await TerminalSession.create(
        workspace_id=workspace_id,
        title=title or "Terminal",
        cwd=ws.root_path,
    )
    pty_manager.attach(str(row.id), ws.root_path, cols, rows)
    return row
