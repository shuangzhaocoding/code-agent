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
    def __init__(
        self,
        session_id: str,
        cwd: str,
        shell: str,
        *,
        env_extra: dict[str, str] | None = None,
        workspace_root: str | None = None,
        activate_cmd: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.shell = shell
        self.env_extra = dict(env_extra or {})
        self.workspace_root = workspace_root
        self.activate_cmd = activate_cmd
        self.pid: int | None = None
        self.buffer = bytearray()
        self.max_buf = int(settings.get("terminal.scrollback_bytes") or 204800)
        self.subscribers: list[WebSocket] = []
        self.alive = False

    def _send_activation(self) -> None:
        cmd = (self.activate_cmd or "").strip()
        if not cmd or not self.alive:
            return
        nl = "\r\n" if sys.platform == "win32" else "\n"
        line = cmd if cmd.endswith(("\n", "\r")) else f"{cmd}{nl}"
        try:
            self.write(line.encode("utf-8"))
        except Exception:
            pass

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
    def __init__(
        self,
        session_id: str,
        cwd: str,
        shell: str,
        *,
        env_extra: dict[str, str] | None = None,
        workspace_root: str | None = None,
        activate_cmd: str | None = None,
    ) -> None:
        super().__init__(
            session_id,
            cwd,
            shell,
            env_extra=env_extra,
            workspace_root=workspace_root,
            activate_cmd=activate_cmd,
        )
        self.fd: int | None = None

    def spawn(self, cols: int, rows: int) -> None:
        import fcntl
        import pty
        import termios

        from code_agent.runtime.python_env import merge_python_env
        from code_agent.runtime.python_env import PythonEnv

        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.cwd)
            pyenv = PythonEnv(env=self.env_extra) if self.env_extra else None
            env = merge_python_env(os.environ, pyenv)
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["CLICOLOR"] = "1"
            env["CLICOLOR_FORCE"] = "1"
            env["FORCE_COLOR"] = "1"
            # Interactive non-login when a venv is active so login profiles do not clobber PATH.
            shell_args = [self.shell, "-i"] if self.env_extra.get("VIRTUAL_ENV") else [self.shell, "-il"]
            os.execvpe(self.shell, shell_args, env)
        self.pid = pid
        self.fd = fd
        self.alive = True
        self.resize(cols, rows)
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        loop = asyncio.get_running_loop()
        loop.add_reader(fd, self._on_data)
        # Let the shell finish rc files, then source activate.
        loop.call_later(0.15, self._send_activation)

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

    def __init__(
        self,
        session_id: str,
        cwd: str,
        shell: str,
        *,
        env_extra: dict[str, str] | None = None,
        workspace_root: str | None = None,
        activate_cmd: str | None = None,
    ) -> None:
        super().__init__(
            session_id,
            cwd,
            shell,
            env_extra=env_extra,
            workspace_root=workspace_root,
            activate_cmd=activate_cmd,
        )
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

        from code_agent.runtime.python_env import PythonEnv, merge_python_env

        cwd = self.cwd if os.path.isdir(self.cwd) else os.path.expanduser("~")
        pyenv = PythonEnv(env=self.env_extra) if self.env_extra else None
        env = merge_python_env(os.environ, pyenv)
        used_env = False
        try:
            self._proc = PtyProcess.spawn(
                self.shell,
                cwd=cwd,
                dimensions=(rows, cols),
                env=env,
            )
            used_env = True
        except TypeError:
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
        # Always try to source/call activate so prompt shows (.venv).
        self._loop.call_later(0.25, self._send_activation)
        if not used_env and not self.activate_cmd and self.env_extra.get("VIRTUAL_ENV"):
            try:
                venv = self.env_extra.get("VIRTUAL_ENV", "")
                path = self.env_extra.get("PATH", "")
                shell_l = self.shell.lower()
                if "powershell" in shell_l or "pwsh" in shell_l:
                    cmd = (
                        f'$env:VIRTUAL_ENV="{venv}"; $env:PATH="{path}"; '
                        f"Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue\r\n"
                    )
                else:
                    cmd = f'set "VIRTUAL_ENV={venv}" & set "PATH={path}" & set "PYTHONHOME="\r\n'
                self.write(cmd.encode("utf-8"))
            except Exception:
                pass

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


def _new_handle(
    session_id: str,
    cwd: str,
    shell: str,
    *,
    env_extra: dict[str, str] | None = None,
    workspace_root: str | None = None,
    activate_cmd: str | None = None,
) -> _BasePtyHandle:
    kwargs = dict(
        env_extra=env_extra,
        workspace_root=workspace_root,
        activate_cmd=activate_cmd,
    )
    if sys.platform == "win32":
        return WinPtyHandle(session_id, cwd, shell, **kwargs)
    return UnixPtyHandle(session_id, cwd, shell, **kwargs)


class PtyManager:
    def __init__(self) -> None:
        self._sessions: dict[str, _BasePtyHandle] = {}

    def get(self, session_id: str) -> _BasePtyHandle | None:
        return self._sessions.get(session_id)

    def attach(
        self,
        session_id: str,
        cwd: str,
        cols: int,
        rows: int,
        *,
        env_extra: dict[str, str] | None = None,
        workspace_root: str | None = None,
        activate_cmd: str | None = None,
    ) -> _BasePtyHandle:
        handle = self._sessions.get(session_id)
        if handle and handle.alive:
            return handle
        shell = _default_shell()
        handle = _new_handle(
            session_id,
            cwd,
            shell,
            env_extra=env_extra,
            workspace_root=workspace_root,
            activate_cmd=activate_cmd,
        )
        handle.spawn(cols, rows)
        self._sessions[session_id] = handle
        return handle

    def drop(self, session_id: str) -> None:
        handle = self._sessions.pop(session_id, None)
        if handle:
            handle.close()


pty_manager = PtyManager()


async def create_terminal(
    workspace_id: str, title: str | None = None, cwd: str | None = None
) -> TerminalSession:
    from code_agent.runtime.python_env import terminal_title_with_env
    from code_agent.workspace.backend import workspace_is_ssh
    from code_agent.workspace.ssh import _posix_join
    from code_agent.tools.paths import resolve_in_workspace

    ws = await Workspace.get(id=workspace_id)
    cols = int(settings.get("terminal.default_cols") or 120)
    rows = int(settings.get("terminal.default_rows") or 32)
    rel = (cwd or "").strip().replace("\\", "/").strip("/")
    if workspace_is_ssh(ws):
        start_cwd = _posix_join(ws.root_path, rel or ".")
    else:
        try:
            resolved = resolve_in_workspace(ws.root_path, rel or ".")
            start_cwd = str(resolved if resolved.is_dir() else resolved.parent)
        except Exception:
            start_cwd = ws.root_path
    pyenv = await _resolve_terminal_pyenv(ws)
    label = title
    if not label:
        leaf = rel.split("/")[-1] if rel else ""
        if workspace_is_ssh(ws):
            label = f"SSH · {leaf}" if leaf else "SSH Terminal"
        else:
            label = leaf or "Terminal"
        label = terminal_title_with_env(label, pyenv)
    row = await TerminalSession.create(
        workspace_id=workspace_id,
        title=label,
        cwd=start_cwd,
    )
    await pty_manager.attach_workspace(str(row.id), ws, cols, rows, cwd=start_cwd)
    return row


class SshPtyHandle(_BasePtyHandle):
    def __init__(
        self,
        session_id: str,
        cwd: str,
        shell: str,
        *,
        env_extra: dict[str, str] | None = None,
        workspace_root: str | None = None,
        activate_cmd: str | None = None,
    ) -> None:
        super().__init__(
            session_id,
            cwd,
            shell,
            env_extra=env_extra,
            workspace_root=workspace_root,
            activate_cmd=activate_cmd,
        )
        self._process = None
        self._reader_task: asyncio.Task | None = None
        self._conn_key = ""

    @classmethod
    async def create(
        cls,
        session_id: str,
        ws: Workspace,
        cols: int,
        rows: int,
        cwd: str | None = None,
        *,
        env_extra: dict[str, str] | None = None,
        activate_cmd: str | None = None,
    ) -> SshPtyHandle:
        from code_agent.runtime.python_env import PythonEnv, shell_export_prefix
        from code_agent.workspace.ssh import SshWorkspaceBackend

        backend = await SshWorkspaceBackend.open(ws)
        conn = await backend._conn()
        shell = _default_shell()
        # Prefer remote login shell in workspace (or requested) cwd
        import shlex

        start = (cwd or ws.root_path).strip() or ws.root_path
        pyenv = PythonEnv(env=dict(env_extra or {})) if env_extra else None
        activate = shell_export_prefix(pyenv, windows=False)
        # Interactive non-login when env is injected so remote profile does not reset PATH.
        shell_flag = "-i" if env_extra and env_extra.get("VIRTUAL_ENV") else "-l"
        cmd = f"cd {shlex.quote(start)} && {activate}exec \"$SHELL\" {shell_flag}"
        process = await conn.create_process(
            cmd,
            term_type="xterm-256color",
            term_size=(rows, cols),
        )
        handle = cls(
            session_id,
            start,
            shell,
            env_extra=env_extra,
            workspace_root=ws.root_path,
            activate_cmd=activate_cmd,
        )
        handle._process = process
        handle._conn_key = str(ws.id)
        handle.alive = True
        handle.pid = None
        handle._reader_task = asyncio.create_task(handle._read_loop())
        # After remote shell starts, source activate so the prompt shows the venv.
        loop = asyncio.get_running_loop()
        loop.call_later(0.2, handle._send_activation)
        return handle

    async def _read_loop(self) -> None:
        assert self._process is not None
        try:
            while self.alive:
                data = await self._process.stdout.read(4096)
                if not data:
                    break
                chunk = data.encode("utf-8", errors="replace") if isinstance(data, str) else bytes(data)
                self._append(chunk)
                await self._broadcast(chunk)
        except Exception:
            pass
        self.alive = False
        await self._broadcast_exit()

    def spawn(self, cols: int, rows: int) -> None:
        raise RuntimeError("SshPtyHandle must be created via create()")

    def resize(self, cols: int, rows: int) -> None:
        if self._process is None:
            return
        try:
            self._process.change_terminal_size(cols, rows)
        except Exception:
            try:
                self._process.term_size = (rows, cols)
            except Exception:
                pass

    def write(self, data: bytes) -> None:
        if self._process is None or not self.alive:
            return
        text = data.decode("utf-8", errors="replace")
        try:
            self._process.stdin.write(text)
        except Exception:
            self.alive = False

    def close(self) -> None:
        self.alive = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        proc = self._process
        self._process = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                try:
                    proc.close()
                except Exception:
                    pass


# Patch PtyManager with async workspace attach
_orig_attach = PtyManager.attach


async def _resolve_terminal_pyenv(ws: Workspace):
    from code_agent.runtime.python_env import discover_workspace_venv_remote, resolve_python_env
    from code_agent.workspace.backend import get_workspace_backend, workspace_is_ssh

    pyenv = resolve_python_env(workspace_root=ws.root_path)
    if pyenv.active or not workspace_is_ssh(ws):
        return pyenv

    backend = await get_workspace_backend(ws)
    try:
        import yaml

        try:
            text = await backend.read_text(".code-agent/config.yaml")
            cfg = yaml.safe_load(text) if text.strip() else {}
            python_cfg = (cfg or {}).get("python") if isinstance(cfg, dict) else None
            raw = python_cfg.get("interpreter") if isinstance(python_cfg, dict) else None
            if raw and str(raw).strip():
                return resolve_python_env(workspace_root=ws.root_path, configured=str(raw).strip())
        except Exception:
            pass

        discovered = await discover_workspace_venv_remote(backend)
        if discovered:
            return resolve_python_env(workspace_root=ws.root_path, configured=discovered)
    finally:
        await backend.close()
    return pyenv


async def _attach_workspace(
    self: PtyManager, session_id: str, ws: Workspace, cols: int, rows: int, cwd: str | None = None
) -> _BasePtyHandle:
    from code_agent.runtime.python_env import activation_shell_command
    from code_agent.workspace.backend import workspace_is_ssh

    existing = self._sessions.get(session_id)
    if existing and existing.alive:
        return existing
    start = (cwd or ws.root_path).strip() or ws.root_path
    pyenv = await _resolve_terminal_pyenv(ws)
    env_extra = pyenv.env if pyenv.active else None
    shell = _default_shell()
    activate_cmd = activation_shell_command(
        pyenv,
        windows=sys.platform == "win32",
        shell=shell,
        cwd=start,
        workspace_root=ws.root_path,
    )
    if workspace_is_ssh(ws):
        handle = await SshPtyHandle.create(
            session_id,
            ws,
            cols,
            rows,
            cwd=start,
            env_extra=env_extra,
            activate_cmd=activation_shell_command(
                pyenv,
                windows=False,
                shell=shell,
                cwd=start,
                workspace_root=ws.root_path,
            ),
        )
        self._sessions[session_id] = handle
        return handle
    return _orig_attach(
        self,
        session_id,
        start,
        cols,
        rows,
        env_extra=env_extra,
        workspace_root=ws.root_path,
        activate_cmd=activate_cmd,
    )


PtyManager.attach_workspace = _attach_workspace  # type: ignore[attr-defined]
