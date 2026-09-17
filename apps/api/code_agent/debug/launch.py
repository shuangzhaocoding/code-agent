"""Resolve Python debug launch configs (launch.json + current file)."""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_VAR_RE = re.compile(r"\$\{([^}]+)\}")

# launch.json / defaults often say "python3"; on Windows that is frequently a Store stub.
_GENERIC_PYTHON_NAMES = frozenset({"python", "python3", "python3.11", "python3.12", "py"})


def resolve_debug_python(
    configured: str | None,
    *,
    is_ssh: bool = False,
    workspace_root: str | None = None,
    settings_interpreter: str | None = None,
) -> str:
    """Pick the interpreter used to launch debugpy.

    Preference for local generic names (``python3`` / ``python``):
    1. Settings ``python.interpreter`` (workspace venv)
    2. ``sys.executable`` (desktop bundled CPython with debugpy)
    3. Platform default

    Remote SSH: use a concrete launch.json path when set; otherwise prefer
    ``settings_interpreter`` (loaded from the remote ``.code-agent/config.yaml``)
    via soft path resolve. Do not read the remote path as a local file.
    """
    raw = (configured or "").strip()
    name = Path(raw).name.lower() if raw else ""
    # Strip .exe on Windows for comparison.
    if name.endswith(".exe"):
        name = name[:-4]
    generic = (not raw) or (name in _GENERIC_PYTHON_NAMES and ("/" not in raw.replace("\\", "/")))
    if is_ssh:
        if raw and not generic:
            return raw
        try:
            from code_agent.runtime.python_env import resolve_python_env

            # settings_interpreter is required for SSH when the setting lives only on the remote.
            # Pass "" when the caller already checked remote and found nothing (skip local yaml).
            if settings_interpreter is not None:
                pyenv = resolve_python_env(
                    workspace_root=workspace_root,
                    configured=settings_interpreter.strip(),
                )
            else:
                pyenv = resolve_python_env(workspace_root=workspace_root)
            if pyenv.python:
                return pyenv.python
        except Exception:
            pass
        return "python3"
    if raw and not generic:
        return raw
    try:
        from code_agent.runtime.python_env import resolve_python_env

        if settings_interpreter is not None and str(settings_interpreter).strip():
            pyenv = resolve_python_env(
                workspace_root=workspace_root,
                configured=str(settings_interpreter).strip(),
            )
        else:
            pyenv = resolve_python_env(workspace_root=workspace_root)
        if pyenv.python:
            return pyenv.python
    except Exception:
        pass
    exe = (sys.executable or "").strip()
    if exe:
        return exe
    return "python" if os.name == "nt" else "python3"


@dataclass
class LaunchConfig:
    name: str = "Python"
    request: str = "launch"
    program: str | None = None  # workspace-relative or absolute
    module: str | None = None
    cwd: str = "."  # workspace-relative
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    python: str = "python3"
    stop_on_entry: bool = False
    just_my_code: bool = True


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _expand(value: str, *, workspace_root: str, current_file: str | None) -> str:
    file_path = current_file or ""
    file_abs = (
        file_path
        if os.path.isabs(file_path)
        else os.path.normpath(os.path.join(workspace_root, file_path))
        if file_path
        else ""
    )
    file_dir = os.path.dirname(file_abs) if file_abs else workspace_root

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in {"workspaceFolder", "workspaceRoot"}:
            return workspace_root
        if key == "file":
            return file_abs
        if key == "fileBasename":
            return os.path.basename(file_abs) if file_abs else ""
        if key == "fileDirname":
            return file_dir
        if key == "fileExtname":
            return os.path.splitext(file_abs)[1] if file_abs else ""
        if key.startswith("env:"):
            return os.environ.get(key[4:], "")
        return match.group(0)

    return _VAR_RE.sub(repl, value)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


def _as_env(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def parse_launch_entry(raw: dict[str, Any]) -> LaunchConfig:
    return LaunchConfig(
        name=str(raw.get("name") or "Python"),
        request=str(raw.get("request") or "launch"),
        program=str(raw["program"]) if raw.get("program") else None,
        module=str(raw["module"]) if raw.get("module") else None,
        cwd=str(raw.get("cwd") or "${workspaceFolder}"),
        args=_as_str_list(raw.get("args")),
        env=_as_env(raw.get("env")),
        python=str(raw.get("python") or raw.get("pythonPath") or "python3"),
        stop_on_entry=bool(raw.get("stopOnEntry")),
        just_my_code=bool(raw.get("justMyCode", True)),
    )


def default_current_file_config(rel_path: str) -> LaunchConfig:
    parent = str(Path(rel_path).parent).replace("\\", "/")
    if parent in {".", ""}:
        parent = "."
    return LaunchConfig(
        name="Python: Current File",
        program=rel_path,
        cwd=parent,
        python="python3",
        stop_on_entry=False,
    )


def load_launch_configs_from_text(text: str) -> list[LaunchConfig]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = data.get("configurations") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[LaunchConfig] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        typ = str(row.get("type") or "").lower()
        if typ and typ not in {"python", "debugpy", "python-debugpy"}:
            continue
        out.append(parse_launch_entry(row))
    return out


def expand_config(
    cfg: LaunchConfig,
    *,
    workspace_root: str,
    current_file: str | None,
) -> LaunchConfig:
    program = _expand(cfg.program, workspace_root=workspace_root, current_file=current_file) if cfg.program else None
    module = _expand(cfg.module, workspace_root=workspace_root, current_file=current_file) if cfg.module else None
    cwd = _expand(cfg.cwd or ".", workspace_root=workspace_root, current_file=current_file)
    args = [_expand(a, workspace_root=workspace_root, current_file=current_file) for a in cfg.args]
    env = {
        k: _expand(v, workspace_root=workspace_root, current_file=current_file) for k, v in cfg.env.items()
    }
    python = _expand(cfg.python or "python3", workspace_root=workspace_root, current_file=current_file)
    # Prefer workspace-relative program when under root
    if program and os.path.isabs(program):
        try:
            rel = os.path.relpath(program, workspace_root)
            if not rel.startswith(".."):
                program = rel.replace("\\", "/")
        except ValueError:
            pass
    if cwd and os.path.isabs(cwd):
        try:
            rel_cwd = os.path.relpath(cwd, workspace_root)
            if not rel_cwd.startswith(".."):
                cwd = rel_cwd.replace("\\", "/") or "."
        except ValueError:
            pass
    return LaunchConfig(
        name=cfg.name,
        request=cfg.request,
        program=program,
        module=module,
        cwd=cwd or ".",
        args=args,
        env=env,
        python=python or "python3",
        stop_on_entry=cfg.stop_on_entry,
        just_my_code=cfg.just_my_code,
    )


def build_debugpy_argv(cfg: LaunchConfig, *, listen_host: str, listen_port: int) -> list[str]:
    """Argv to start the debuggee (debugpy hosts DAP on listen_port)."""
    argv = [
        cfg.python or "python3",
        "-Xfrozen_modules=off",
        "-m",
        "debugpy",
        "--listen",
        f"{listen_host}:{listen_port}",
        "--wait-for-client",
    ]
    if cfg.module:
        argv.extend(["-m", cfg.module, *cfg.args])
    elif cfg.program:
        # Prefer basename when cwd is the file directory (local/ssh shell cwd).
        prog = cfg.program.replace("\\", "/")
        argv.append(prog)
        argv.extend(cfg.args)
    else:
        raise ValueError("launch config needs program or module")
    return argv


def shell_quote_unix(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def build_remote_shell_command(argv: list[str], *, cwd: str, env: dict[str, str]) -> str:
    exports = " ".join(f"{k}={shell_quote_unix(v)}" for k, v in env.items())
    cmd = " ".join(shell_quote_unix(a) for a in argv)
    prefix = f"cd {shell_quote_unix(cwd)} && "
    if exports:
        prefix += f"env {exports} "
    return prefix + cmd
