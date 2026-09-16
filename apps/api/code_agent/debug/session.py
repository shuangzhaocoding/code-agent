"""One Python debug session (local subprocess or SSH + port forward)."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from code_agent.debug.dap import DapClient
from code_agent.debug.launch import (
    LaunchConfig,
    build_debugpy_argv,
    build_remote_shell_command,
    free_port,
    resolve_debug_python,
)
from code_agent.db.models import Workspace
from code_agent.tools.paths import resolve_in_workspace
from code_agent.workspace.backend import workspace_is_ssh


BroadcastFn = Callable[[dict[str, Any]], Awaitable[None]]

# debugpy/ptvsd often echo their package names (and similar chatter) into the debug console.
_ADAPTER_NOISE_RE = re.compile(
    r"^\s*(?:ptvsd|debugpy|pydevd)(?:\s|$|/|\\|:)",
    re.IGNORECASE,
)


def _is_debug_adapter_noise(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    if raw.lower() in {"ptvsd", "debugpy", "pydevd"}:
        return True
    if _ADAPTER_NOISE_RE.match(raw):
        return True
    # Single-token module dump lines from the adapter.
    if "\n" not in raw and raw.lower().rstrip(".") in {"ptvsd", "debugpy", "pydevd"}:
        return True
    return False


class DebugSession:
    def __init__(
        self,
        *,
        workspace: Workspace,
        config: LaunchConfig,
        breakpoints: dict[str, list[dict[str, Any]]],
        exception_filters: list[str] | None = None,
        broadcast: BroadcastFn | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.workspace = workspace
        self.config = config
        self.breakpoints = {k: list(v) for k, v in (breakpoints or {}).items()}
        self.exception_filters = exception_filters or ["uncaught"]
        self.broadcast = broadcast
        self.state = "starting"
        self.thread_id: int | None = None
        self.dap = DapClient()
        self._proc: asyncio.subprocess.Process | None = None
        self._ssh_proc: Any = None
        self._ssh_listener: Any = None
        self._ssh_conn: Any = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._local_port = 0
        self._remote_port = 0
        self._root = str(workspace.root_path)
        self._ssh = workspace_is_ssh(workspace)
        # Buffer stdout until the first WebSocket client catches up.
        self._output_buffer: list[dict[str, Any]] = []
        self._capture_output = True

    async def _emit(self, typ: str, payload: dict[str, Any] | None = None) -> None:
        body = payload or {}
        if typ == "output" and self._capture_output:
            self._output_buffer.append(dict(body))
            if len(self._output_buffer) > 500:
                self._output_buffer = self._output_buffer[-500:]
        if self.broadcast:
            await self.broadcast({"type": typ, "session_id": self.id, "payload": body})

    def take_output_buffer(self) -> list[dict[str, Any]]:
        """Return and clear buffered output; stop buffering (live WS takes over)."""
        self._capture_output = False
        rows = [dict(row) for row in self._output_buffer]
        self._output_buffer.clear()
        return rows

    def _abs_local(self, rel: str) -> str:
        return str(resolve_in_workspace(self._root, rel))

    def _abs_remote(self, rel: str) -> str:
        root = self._root.rstrip("/") or "/"
        raw = (rel or "").strip().replace("\\", "/")
        if not raw or raw == ".":
            return root
        if raw.startswith("/"):
            return raw
        return f"{root}/{raw}".replace("//", "/")

    def _to_client_path(self, path: str | None) -> str | None:
        if not path:
            return path
        p = path.replace("\\", "/")
        root = self._root.replace("\\", "/").rstrip("/")
        if p == root:
            return ""
        prefix = root + "/"
        if p.startswith(prefix):
            return p[len(prefix) :]
        try:
            rel = os.path.relpath(p, root)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
        return path

    async def snapshot(self) -> dict[str, Any]:
        frames: list[dict[str, Any]] = []
        if self.state == "paused":
            try:
                frames = await self.stack_trace(self.thread_id)
            except Exception:
                frames = []
        top = frames[0] if frames else None
        return {
            "id": self.id,
            "state": self.state,
            "threadId": self.thread_id,
            "frames": frames,
            "program": self.config.program,
            "module": self.config.module,
            "cwd": self.config.cwd,
            "name": self.config.name,
            "currentPath": top.get("path") if isinstance(top, dict) else None,
            "currentLine": top.get("line") if isinstance(top, dict) else None,
        }

    def _source_path_for_dap(self, rel: str) -> str:
        if self._ssh:
            return self._abs_remote(rel)
        return self._abs_local(rel)

    async def start(self) -> None:
        self.dap.set_event_handler(self._on_dap_event)
        try:
            if self._ssh:
                await self._start_ssh()
            else:
                await self._start_local()
            await self._handshake()
            if self.state != "paused":
                self.state = "running"
                await self._emit("session", {"state": self.state})
        except Exception as exc:
            self.state = "error"
            await self._emit("error", {"message": str(exc)})
            await self.stop()
            raise

    async def _debugpy_import_ok(self, python: str) -> tuple[bool, str]:
        """Return (ok, detail). detail is version on success or error text on failure."""
        if self._ssh:
            from code_agent.workspace.ssh import SshWorkspaceBackend

            backend = await SshWorkspaceBackend.open(self.workspace)
            try:
                code, out, err = await backend.run_command(
                    f"{shlex.quote(python)} -c \"import debugpy; print(debugpy.__version__)\"",
                    cwd=".",
                    timeout=30,
                )
            finally:
                await backend.close()
            if code == 0:
                return True, (out or "").strip()
            return False, (err or out or "").strip()
        proc = await asyncio.create_subprocess_exec(
            python,
            "-c",
            "import debugpy; print(debugpy.__version__)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        out = (out_b or b"").decode(errors="replace").strip()
        err = (err_b or b"").decode(errors="replace").strip()
        if proc.returncode == 0:
            return True, out
        return False, err or out

    async def _install_debugpy(self, python: str) -> tuple[bool, str]:
        """Try `python -m pip install debugpy`. Returns (ok, log)."""
        pip_cmd = [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "debugpy",
        ]
        if self._ssh:
            from code_agent.workspace.ssh import SshWorkspaceBackend

            backend = await SshWorkspaceBackend.open(self.workspace)
            try:
                code, out, err = await backend.run_command(
                    " ".join(shlex.quote(p) for p in pip_cmd),
                    cwd=".",
                    timeout=180,
                )
            finally:
                await backend.close()
            detail = "\n".join(x for x in [(out or "").strip(), (err or "").strip()] if x)
            return code == 0, detail
        proc = await asyncio.create_subprocess_exec(
            *pip_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        detail = "\n".join(
            x
            for x in [
                (out_b or b"").decode(errors="replace").strip(),
                (err_b or b"").decode(errors="replace").strip(),
            ]
            if x
        )
        return proc.returncode == 0, detail

    async def _ensure_debugpy(self, python: str) -> None:
        ok, detail = await self._debugpy_import_ok(python)
        if ok:
            return
        where = "remote" if self._ssh else "local"
        await self._emit(
            "output",
            {
                "category": "console",
                "output": f"debugpy not found in {where} Python ({python}); installing…\n",
            },
        )
        installed, install_log = await self._install_debugpy(python)
        ok2, detail2 = await self._debugpy_import_ok(python)
        if installed and ok2:
            await self._emit(
                "output",
                {
                    "category": "console",
                    "output": f"debugpy {detail2 or 'installed'} ready.\n",
                },
            )
            return
        bits = [x for x in [detail, install_log, detail2] if x]
        raise RuntimeError(
            f"{'Remote ' if self._ssh else ''}Python missing debugpy and auto-install failed. "
            f"Install with: {python} -m pip install debugpy\n" + "\n".join(bits)
        )

    async def _start_local(self) -> None:
        python = resolve_debug_python(self.config.python, is_ssh=False, workspace_root=self._root)
        self.config.python = python
        await self._ensure_debugpy(python)
        self._local_port = free_port()
        cwd_path = resolve_in_workspace(self._root, self.config.cwd or ".")
        if not cwd_path.is_dir():
            cwd_path = Path(self._root)
        argv = build_debugpy_argv(self.config, listen_host="127.0.0.1", listen_port=self._local_port)
        # When program is under cwd, pass basename so relative imports work.
        if self.config.program and not self.config.module:
            prog_abs = self._abs_local(self.config.program)
            try:
                rel_to_cwd = os.path.relpath(prog_abs, str(cwd_path))
                if not rel_to_cwd.startswith(".."):
                    # replace last path arg
                    argv = list(argv)
                    for i in range(len(argv) - 1, -1, -1):
                        if argv[i] == self.config.program or argv[i].endswith(self.config.program.replace("\\", "/")):
                            argv[i] = rel_to_cwd
                            break
            except ValueError:
                pass
        env = os.environ.copy()
        env.update(self.config.env)
        env.setdefault("PYTHONUNBUFFERED", "1")
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stdout_task = asyncio.create_task(self._pump_pipe(self._proc.stdout, "stdout"))
        self._stderr_task = asyncio.create_task(self._pump_pipe(self._proc.stderr, "stderr"))
        self._wait_task = asyncio.create_task(self._wait_local_proc())
        await self.dap.connect("127.0.0.1", self._local_port, timeout=30.0)

    async def _start_ssh(self) -> None:
        from code_agent.workspace.ssh import SshWorkspaceBackend
        from code_agent.workspace.ssh_pool import ssh_pool

        python = resolve_debug_python(self.config.python, is_ssh=True, workspace_root=self._root)
        self.config.python = python
        await self._ensure_debugpy(python)
        backend = await SshWorkspaceBackend.open(self.workspace)
        self._ssh_conn = await backend._conn()  # noqa: SLF001 — reuse pooled connection
        # Pick a free remote port
        code, out, err = await backend.run_command(
            "python3 -c \"import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()\"",
            cwd=".",
            timeout=15,
        )
        if code != 0:
            await backend.close()
            raise RuntimeError(f"Failed to allocate remote debug port: {err or out}")
        self._remote_port = int((out or "").strip().splitlines()[-1])
        remote_cwd = self._abs_remote(self.config.cwd or ".")
        cfg = LaunchConfig(
            name=self.config.name,
            program=self.config.program,
            module=self.config.module,
            cwd=self.config.cwd,
            args=list(self.config.args),
            env=dict(self.config.env),
            python=python,
            stop_on_entry=self.config.stop_on_entry,
            just_my_code=self.config.just_my_code,
        )
        argv = build_debugpy_argv(cfg, listen_host="127.0.0.1", listen_port=self._remote_port)
        if cfg.program and not cfg.module:
            prog_abs = self._abs_remote(cfg.program)
            # Prefer path relative to remote cwd when possible
            if prog_abs.startswith(remote_cwd.rstrip("/") + "/"):
                argv = list(argv)
                argv[-1 - len(cfg.args) if cfg.args else -1] = prog_abs[len(remote_cwd.rstrip("/")) + 1 :]
            else:
                argv = list(argv)
                for i in range(len(argv) - 1, -1, -1):
                    if argv[i] == cfg.program:
                        argv[i] = prog_abs
                        break
        remote_cmd = build_remote_shell_command(argv, cwd=remote_cwd, env={**cfg.env, "PYTHONUNBUFFERED": "1"})
        self._ssh_proc = await self._ssh_conn.create_process(remote_cmd)
        self._stdout_task = asyncio.create_task(self._pump_ssh_stream(self._ssh_proc.stdout, "stdout"))
        self._stderr_task = asyncio.create_task(self._pump_ssh_stream(self._ssh_proc.stderr, "stderr"))
        self._wait_task = asyncio.create_task(self._wait_ssh_proc())
        # Local forward → remote debugpy
        self._local_port = free_port()
        self._ssh_listener = await self._ssh_conn.forward_local_port(
            "127.0.0.1",
            self._local_port,
            "127.0.0.1",
            self._remote_port,
        )
        await self.dap.connect("127.0.0.1", self._local_port, timeout=45.0)
        # keep backend pool connection; do not close backend (would drop pool if last user)

    async def _handshake(self) -> None:
        await self.dap.request(
            "initialize",
            {
                "clientID": "code-agent",
                "clientName": "Code Agent",
                "adapterID": "python",
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
                "supportsVariablePaging": False,
                "supportsRunInTerminalRequest": False,
                "locale": "en-us",
            },
        )
        # debugpy sends `initialized` only after attach is received, and answers
        # attach after configurationDone — fire attach without awaiting first.
        attach_fut = await self.dap.request_start(
            "attach",
            {
                "name": self.config.name,
                "type": "python",
                "request": "attach",
                "justMyCode": self.config.just_my_code,
            },
        )
        try:
            await self.dap.wait_initialized(timeout=15.0)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("debugpy did not send initialized event") from exc
        await self._apply_all_breakpoints()
        await self.dap.request(
            "setExceptionBreakpoints",
            {"filters": list(self.exception_filters)},
        )
        await self.dap.request("configurationDone", {})
        try:
            await asyncio.wait_for(attach_fut, timeout=15.0)
        except Exception:
            pass
        if self.config.stop_on_entry and self.state != "paused":
            # Process starts after configurationDone; pause ASAP for a first-line stop.
            for _ in range(20):
                if self.state == "paused":
                    break
                try:
                    await self.dap.request("pause", {"threadId": self.thread_id or 1})
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        elif self.breakpoints and self.state != "paused":
            # Give breakpoint hits a moment to arrive before returning "running".
            for _ in range(30):
                if self.state == "paused":
                    break
                await asyncio.sleep(0.05)

    async def _apply_all_breakpoints(self) -> None:
        for rel, bps in self.breakpoints.items():
            await self._set_breakpoints_file(rel, bps)

    async def _set_breakpoints_file(self, rel: str, bps: list[dict[str, Any]]) -> dict[str, Any]:
        source_path = self._source_path_for_dap(rel)
        args = {
            "source": {"path": source_path, "name": Path(rel).name},
            "breakpoints": [
                {
                    "line": int(bp["line"]),
                    **({"condition": bp["condition"]} if bp.get("condition") else {}),
                    **({"hitCondition": bp["hitCondition"]} if bp.get("hitCondition") else {}),
                    **({"logMessage": bp["logMessage"]} if bp.get("logMessage") else {}),
                }
                for bp in bps
                if int(bp.get("line") or 0) > 0
            ],
            "sourceModified": False,
        }
        try:
            resp = await self.dap.request("setBreakpoints", args)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        return {"ok": True, "breakpoints": body.get("breakpoints") or []}

    async def set_breakpoints(self, rel: str, bps: list[dict[str, Any]]) -> dict[str, Any]:
        self.breakpoints[rel] = list(bps)
        if not self.dap.connected:
            return {"ok": True, "deferred": True}
        return await self._set_breakpoints_file(rel, bps)

    async def set_exception_breakpoints(self, filters: list[str]) -> None:
        self.exception_filters = list(filters)
        if self.dap.connected:
            await self.dap.request("setExceptionBreakpoints", {"filters": list(filters)})

    async def continue_(self, thread_id: int | None = None) -> None:
        tid = thread_id or self.thread_id or 1
        await self.dap.request("continue", {"threadId": tid})
        self.state = "running"
        await self._emit("session", {"state": self.state})

    async def next(self, thread_id: int | None = None) -> None:
        tid = thread_id or self.thread_id or 1
        await self.dap.request("next", {"threadId": tid})

    async def step_in(self, thread_id: int | None = None) -> None:
        tid = thread_id or self.thread_id or 1
        await self.dap.request("stepIn", {"threadId": tid})

    async def step_out(self, thread_id: int | None = None) -> None:
        tid = thread_id or self.thread_id or 1
        await self.dap.request("stepOut", {"threadId": tid})

    async def pause(self, thread_id: int | None = None) -> None:
        tid = thread_id or self.thread_id or 1
        await self.dap.request("pause", {"threadId": tid})

    async def stack_trace(self, thread_id: int | None = None) -> list[dict[str, Any]]:
        tid = thread_id or self.thread_id or 1
        resp = await self.dap.request("stackTrace", {"threadId": tid, "startFrame": 0, "levels": 50})
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        frames = body.get("stackFrames") or []
        out: list[dict[str, Any]] = []
        for fr in frames:
            if not isinstance(fr, dict):
                continue
            src = fr.get("source") if isinstance(fr.get("source"), dict) else {}
            path = self._to_client_path(src.get("path") if isinstance(src.get("path"), str) else None)
            out.append(
                {
                    "id": fr.get("id"),
                    "name": fr.get("name"),
                    "line": fr.get("line"),
                    "column": fr.get("column"),
                    "path": path,
                    "source": {"path": path, "name": src.get("name")},
                }
            )
        return out

    async def scopes(self, frame_id: int) -> list[dict[str, Any]]:
        resp = await self.dap.request("scopes", {"frameId": frame_id})
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        return list(body.get("scopes") or [])

    async def variables(self, variables_reference: int) -> list[dict[str, Any]]:
        resp = await self.dap.request(
            "variables",
            {"variablesReference": variables_reference},
        )
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        return list(body.get("variables") or [])

    async def evaluate(self, expression: str, frame_id: int | None = None, context: str = "repl") -> dict[str, Any]:
        args: dict[str, Any] = {"expression": expression, "context": context}
        if frame_id is not None:
            args["frameId"] = frame_id
        resp = await self.dap.request("evaluate", args)
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        return {
            "result": body.get("result"),
            "type": body.get("type"),
            "variablesReference": body.get("variablesReference") or 0,
        }

    async def set_variable(
        self,
        variables_reference: int,
        name: str,
        value: str,
    ) -> dict[str, Any]:
        resp = await self.dap.request(
            "setVariable",
            {
                "variablesReference": variables_reference,
                "name": name,
                "value": value,
            },
        )
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        return {
            "name": body.get("name") or name,
            "value": body.get("value"),
            "type": body.get("type"),
            "variablesReference": body.get("variablesReference") or 0,
            "namedVariables": body.get("namedVariables"),
            "indexedVariables": body.get("indexedVariables"),
        }

    async def stop(self) -> None:
        self.state = "stopped"
        try:
            if self.dap.connected:
                try:
                    await self.dap.request("disconnect", {"terminateDebuggee": True}, timeout=3.0)
                except Exception:
                    pass
        finally:
            await self.dap.close()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
            except Exception:
                pass
        if self._ssh_proc is not None:
            try:
                self._ssh_proc.terminate()
            except Exception:
                try:
                    self._ssh_proc.kill()
                except Exception:
                    pass
        if self._ssh_listener is not None:
            try:
                self._ssh_listener.close()
            except Exception:
                pass
            self._ssh_listener = None
        for task in (self._stdout_task, self._stderr_task, self._wait_task):
            if task:
                task.cancel()
        await self._emit("session", {"state": "terminated"})

    async def _on_dap_event(self, event: str, body: dict[str, Any]) -> None:
        if event == "stopped":
            self.state = "paused"
            self.thread_id = int(body.get("threadId") or 1)
            # Emit immediately so the UI unlocks step buttons even before stackTrace returns.
            await self._emit(
                "stopped",
                {
                    "reason": body.get("reason"),
                    "description": body.get("description"),
                    "threadId": self.thread_id,
                    "allThreadsStopped": body.get("allThreadsStopped"),
                    "frames": [],
                },
            )
            await self._emit("session", {"state": self.state})
            frames: list[dict[str, Any]] = []
            try:
                frames = await self.stack_trace(self.thread_id)
            except Exception:
                frames = []
            if frames:
                await self._emit(
                    "stopped",
                    {
                        "reason": body.get("reason"),
                        "description": body.get("description"),
                        "threadId": self.thread_id,
                        "allThreadsStopped": body.get("allThreadsStopped"),
                        "frames": frames,
                    },
                )
            return
        if event == "continued":
            self.state = "running"
            await self._emit("session", {"state": self.state})
            return
        if event == "terminated":
            self.state = "terminated"
            await self._emit("session", {"state": self.state})
            return
        if event == "exited":
            await self._emit("exited", {"exitCode": body.get("exitCode")})
            return
        if event == "output":
            text = str(body.get("output") or "")
            if _is_debug_adapter_noise(text):
                return
            await self._emit(
                "output",
                {
                    "category": body.get("category") or "console",
                    "output": text,
                },
            )
            return
        if event == "thread":
            await self._emit("thread", body)
            return

    async def _pump_pipe(self, stream: asyncio.StreamReader | None, category: str) -> None:
        if not stream:
            return
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace")
                if _is_debug_adapter_noise(text):
                    continue
                await self._emit("output", {"category": category, "output": text})
        except asyncio.CancelledError:
            pass

    async def _pump_ssh_stream(self, stream: Any, category: str) -> None:
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)
                if _is_debug_adapter_noise(text):
                    continue
                await self._emit("output", {"category": category, "output": text})
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _wait_local_proc(self) -> None:
        if not self._proc:
            return
        code = await self._proc.wait()
        await self._emit("exited", {"exitCode": code})
        self.state = "terminated"
        await self._emit("session", {"state": self.state})
        await self.dap.close()

    async def _wait_ssh_proc(self) -> None:
        if not self._ssh_proc:
            return
        try:
            await self._ssh_proc.wait()
            code = getattr(self._ssh_proc, "exit_status", None) or getattr(self._ssh_proc, "returncode", 0)
        except Exception:
            code = -1
        await self._emit("exited", {"exitCode": code})
        self.state = "terminated"
        await self._emit("session", {"state": self.state})
        await self.dap.close()
