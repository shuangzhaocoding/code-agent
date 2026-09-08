from __future__ import annotations

import asyncio
import os
import shutil
import signal
import struct
import sys
import threading
from typing import Any

from fastapi import WebSocket

from code_agent.config import settings
from code_agent.db.models import TerminalSession, Workspace


def _default_shell() -> str:
    configured = (settings.get("terminal.shell") or "").strip()
    if configured:
        return configured
    if sys.platform == "win32":
        return (
            os.environ.get("COMSPEC")
            or shutil.which("pwsh")
            or shutil.which("powershell")
            or shutil.which("cmd")
            or "cmd.exe"
        )
    return (
        os.environ.get("SHELL")
        or shutil.which("zsh")
        or shutil.which("bash")
        or "/bin/bash"
    )


class _BasePtyHandle:
    def __init__(self, session_id: str, cwd: str, shell: str) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.shell = shell
        self.pid: int | None = None
        self.buffer = bytearray()
        self.max_buf = int(settings.get("terminal.scrollback_bytes") or 204800)
        self.subscribers: list[WebSocket] = []
        self.alive = False

    def spawn(self, cols: int, rows: int) -> None:
        raise NotImplementedError

    def resize(self, cols: int, rows: int) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def _append(self, chunk: bytes) -> None:
        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_buf:
            self.buffer = self.buffer[-self.max_buf :]

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


class UnixPtyHandle(_BasePtyHandle):
    def __init__(self, session_id: str, cwd: str, shell: str) -> None:
        super().__init__(session_id, cwd, shell)
        self.fd: int | None = None

    def spawn(self, cols: int, rows: int) -> None:
        import fcntl
        import pty
        import termios

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
        import fcntl
        import termios

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
            try:
                asyncio.get_running_loop().remove_reader(self.fd)
            except Exception:
                pass
            self.alive = False
            asyncio.create_task(self._broadcast_exit())
            return
        self._append(chunk)
        asyncio.create_task(self._broadcast(chunk))

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
            self.fd = None
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGHUP)
            except OSError:
                pass
        self.alive = False


class WinPtyHandle(_BasePtyHandle):
    """Windows ConPTY / winpty via pywinpty (import name: winpty)."""

    def __init__(self, session_id: str, cwd: str, shell: str) -> None:
        super().__init__(session_id, cwd, shell)
        self._proc: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reader: threading.Thread | None = None
        self._closed = False

    def spawn(self, cols: int, rows: int) -> None:
        try:
            from winpty import PtyProcess
        except ImportError as exc:
            raise RuntimeError(
                "Windows terminal requires pywinpty. Install with: pip install pywinpty"
            ) from exc

        cwd = self.cwd if os.path.isdir(self.cwd) else os.path.expanduser("~")
        self._proc = PtyProcess.spawn(
            self.shell,
            cwd=cwd,
            dimensions=(rows, cols),
        )
        self.pid = int(getattr(self._proc, "pid", 0) or 0) or None
        self.alive = True
        self._loop = asyncio.get_running_loop()
        self._reader = threading.Thread(target=self._read_loop, name=f"pty-{self.session_id}", daemon=True)
        self._reader.start()

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is None:
            return
        try:
            self._proc.setwinsize(rows, cols)
        except Exception:
            pass

    def write(self, data: bytes) -> None:
        if self._proc is None or not self.alive:
            return
        text = data.decode("utf-8", errors="replace")
        try:
            self._proc.write(text)
        except Exception:
            self._mark_dead()

    def _read_loop(self) -> None:
        assert self._loop is not None
        while not self._closed and self._proc is not None:
            try:
                if hasattr(self._proc, "isalive") and not self._proc.isalive():
                    break
                data = self._proc.read(4096)
            except Exception:
                break
            if not data:
                # empty read can mean would-block; brief sleep then retry while alive
                if hasattr(self._proc, "isalive") and self._proc.isalive():
                    threading.Event().wait(0.02)
                    continue
                break
            chunk = data.encode("utf-8", errors="replace") if isinstance(data, str) else bytes(data)
            self._loop.call_soon_threadsafe(self._on_chunk, chunk)
        self._loop.call_soon_threadsafe(self._mark_dead)

    def _on_chunk(self, chunk: bytes) -> None:
        if not chunk or not self.alive:
            return
        self._append(chunk)
        asyncio.create_task(self._broadcast(chunk))

    def _mark_dead(self) -> None:
        if not self.alive and self._closed:
            return
        was_alive = self.alive
        self.alive = False
        if was_alive:
            asyncio.create_task(self._broadcast_exit())

    def close(self) -> None:
        self._closed = True
        self.alive = False
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        for meth in ("terminate", "kill", "close"):
            fn = getattr(proc, meth, None)
            if callable(fn):
                try:
                    fn()
                    break
                except Exception:
                    continue


def _new_handle(session_id: str, cwd: str, shell: str) -> _BasePtyHandle:
    if sys.platform == "win32":
        return WinPtyHandle(session_id, cwd, shell)
    return UnixPtyHandle(session_id, cwd, shell)


class PtyManager:
    def __init__(self) -> None:
        self._sessions: dict[str, _BasePtyHandle] = {}

    def get(self, session_id: str) -> _BasePtyHandle | None:
        return self._sessions.get(session_id)

    def attach(self, session_id: str, cwd: str, cols: int, rows: int) -> _BasePtyHandle:
        handle = self._sessions.get(session_id)
        if handle and handle.alive:
            return handle
        shell = _default_shell()
        handle = _new_handle(session_id, cwd, shell)
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
