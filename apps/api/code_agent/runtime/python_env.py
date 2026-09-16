"""Resolve configured workspace Python interpreter into env + display label."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from code_agent.config import get_workspace_setting, settings


@dataclass
class PythonEnv:
    """Activated interpreter for terminals / agent shell commands."""

    python: str | None = None
    venv_root: str | None = None
    label: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return bool(self.env)


def _is_exe(path: Path) -> bool:
    name = path.name.lower()
    if sys.platform == "win32":
        return name in {"python.exe", "python3.exe", "python"} or name.startswith("python")
    return path.is_file() and os.access(path, os.X_OK)


def _venv_root_from_python(python: Path) -> Path | None:
    """Return venv root for …/bin/python or …/Scripts/python.exe."""
    parent = python.parent
    folder = parent.name.lower()
    if folder in {"bin", "scripts"}:
        root = parent.parent
        # Typical venv markers
        if (root / "pyvenv.cfg").is_file() or folder in {"bin", "scripts"}:
            return root
    cfg = python.parent / "pyvenv.cfg"
    if cfg.is_file():
        return python.parent
    return None


def _label_for_venv(venv_root: Path | None, python: Path | None) -> str | None:
    if venv_root is not None:
        name = venv_root.name.strip() or ".venv"
        # Always show a short env tag; prefer literal ".venv" when that is the folder.
        return name if name else ".venv"
    if python is not None:
        return python.name
    return None


def _resolve_path(raw: str, workspace_root: str | None) -> Path:
    text = raw.strip().strip('"').strip("'")
    text = os.path.expanduser(text)
    text = os.path.expandvars(text)
    path = Path(text)
    if not path.is_absolute() and workspace_root:
        path = Path(workspace_root) / path
    try:
        return path.resolve()
    except OSError:
        return path


def _looks_like_python_binary(name: str) -> bool:
    lower = name.lower()
    return lower in {"python", "python3", "python.exe", "python3.exe"} or lower.startswith("python")


_COMMON_VENV_NAMES = (".venv", "venv", "env")


def _is_venv_dir(path: Path) -> bool:
    """True when ``path`` looks like a Python venv root."""
    if not path.is_dir():
        return False
    if (path / "pyvenv.cfg").is_file():
        return True
    if sys.platform == "win32":
        return (path / "Scripts" / "python.exe").is_file()
    return (path / "bin" / "python3").is_file() or (path / "bin" / "python").is_file()


def discover_workspace_venv(workspace_root: str | None) -> str | None:
    """Return a workspace-relative venv path (e.g. ``.venv``) when one exists locally."""
    if not workspace_root:
        return None
    root = Path(workspace_root)
    if not root.is_dir():
        return None
    for name in _COMMON_VENV_NAMES:
        if _is_venv_dir(root / name):
            return name
    return None


async def discover_workspace_venv_remote(backend) -> str | None:
    """Probe remote workspace for ``.venv`` / ``venv`` (SSH backends)."""
    for name in _COMMON_VENV_NAMES:
        markers = (
            [f"{name}/Scripts/python.exe", f"{name}/pyvenv.cfg"]
            if sys.platform == "win32"
            else [f"{name}/pyvenv.cfg", f"{name}/bin/activate"]
        )
        for rel in markers:
            try:
                if await backend.exists(rel):
                    return name
            except Exception:
                continue
    return None


def _venv_python_exe(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    py3 = venv_dir / "bin" / "python3"
    if py3.is_file():
        return py3
    return venv_dir / "bin" / "python"


def _read_python_version(exe: Path) -> str | None:
    if not exe.is_file():
        return None
    try:
        proc = subprocess.run(
            [
                str(exe),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return f"Python {proc.stdout.strip()}"
    except Exception:
        pass
    return None


def _resolve_exe(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _is_windows_store_python(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    return "windowsapps" in str(path).lower().replace("/", "\\")


def _collect_system_python_executables() -> list[Path]:
    """Find system / PATH Python binaries on the machine running the API."""
    out: list[Path] = []
    seen: set[str] = set()

    def add(raw: str | Path | None) -> None:
        if not raw:
            return
        exe = _resolve_exe(Path(str(raw)))
        key = str(exe)
        if key in seen or not exe.is_file() or not _is_exe(exe):
            return
        if _is_windows_store_python(exe):
            return
        seen.add(key)
        out.append(exe)

    add(sys.executable)
    names = ["python3", "python"]
    if sys.platform == "win32":
        names.extend(["python3.exe", "python.exe"])
    else:
        for minor in range(14, 8, -1):
            names.append(f"python3.{minor}")
    for name in names:
        add(shutil.which(name))
    return out


def _append_interpreter_item(
    items: list[dict[str, Any]],
    seen: set[str],
    *,
    path: str,
    version: str | None = None,
    kind: str = "venv",
) -> None:
    text = path.strip()
    if not text or text in seen:
        return
    seen.add(text)
    if kind == "system":
        name = Path(text).name
        label = f"{name} · {version}" if version else text
    else:
        label = text if not version else f"{text} · {version}"
    items.append({"path": text, "label": label, "version": version, "kind": kind})


def _add_system_interpreters(items: list[dict[str, Any]], seen: set[str]) -> None:
    for exe in _collect_system_python_executables():
        version = _read_python_version(exe)
        _append_interpreter_item(
            items,
            seen,
            path=str(exe),
            version=version,
            kind="system",
        )


async def _add_system_interpreters_remote(items: list[dict[str, Any]], seen: set[str], backend) -> None:
    import shlex

    code, stdout, _stderr = await backend.run_command(
        "for c in python3 python; do command -v \"$c\" 2>/dev/null || true; done | awk '!seen[$0]++'",
        cwd=".",
        timeout=12,
    )
    if code not in (0, 124):
        return
    for line in stdout.splitlines():
        raw = line.strip()
        if not raw or raw in seen:
            continue
        version = None
        try:
            _c, ver_out, _ = await backend.run_command(
                f"{shlex.quote(raw)} -c "
                "'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\")'",
                cwd=".",
                timeout=10,
            )
            if _c == 0 and ver_out.strip():
                version = f"Python {ver_out.strip()}"
        except Exception:
            pass
        _append_interpreter_item(items, seen, path=raw, version=version, kind="system")


def discover_python_interpreters_local(
    workspace_root: str,
    *,
    max_nested: int = 24,
) -> list[dict[str, Any]]:
    """Scan a local workspace for venvs to populate settings dropdown."""
    ws = Path(workspace_root).expanduser()
    if not ws.is_dir():
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_venv(venv_dir: Path, rel: str) -> None:
        if not _is_venv_dir(venv_dir):
            return
        version = _read_python_version(_venv_python_exe(venv_dir))
        _append_interpreter_item(items, seen, path=rel, version=version, kind="venv")

    for name in _COMMON_VENV_NAMES:
        add_venv(ws / name, name)

    nested = 0
    try:
        for child in sorted(ws.iterdir(), key=lambda p: p.name.lower()):
            if nested >= max_nested:
                break
            if not child.is_dir() or child.name.startswith("."):
                continue
            nested += 1
            for name in _COMMON_VENV_NAMES:
                candidate = child / name
                if candidate.is_dir():
                    add_venv(candidate, f"{child.name}/{name}")
    except OSError:
        pass

    _add_system_interpreters(items, seen)

    configured = get_workspace_setting(workspace_root, "python.interpreter")
    if configured and str(configured).strip():
        raw = str(configured).strip()
        if raw not in seen:
            resolved = _resolve_path(raw, workspace_root)
            version = None
            if resolved.is_file():
                version = _read_python_version(resolved)
            elif resolved.is_dir() and _is_venv_dir(resolved):
                version = _read_python_version(_venv_python_exe(resolved))
            _append_interpreter_item(items, seen, path=raw, version=version, kind="custom")

    return items


async def discover_python_interpreters_remote(
    backend,
    workspace_root: str,
    *,
    configured: str | None = None,
) -> list[dict[str, Any]]:
    """Probe remote workspace for common venv locations (SSH)."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    async def probe(rel: str) -> bool:
        markers = (
            [f"{rel}/Scripts/python.exe", f"{rel}/pyvenv.cfg"]
            if sys.platform == "win32"
            else [f"{rel}/pyvenv.cfg", f"{rel}/bin/activate", f"{rel}/bin/python3"]
        )
        for marker in markers:
            try:
                if await backend.exists(marker):
                    return True
            except Exception:
                continue
        return False

    for name in _COMMON_VENV_NAMES:
        if await probe(name):
            _append_interpreter_item(items, seen, path=name, kind="venv")

    try:
        for child in await backend.list_dir(""):
            if not child.get("is_dir"):
                continue
            child_name = str(child.get("name") or "")
            if not child_name or child_name.startswith("."):
                continue
            for name in _COMMON_VENV_NAMES:
                rel = f"{child_name}/{name}"
                if await probe(rel):
                    _append_interpreter_item(items, seen, path=rel, kind="venv")
    except Exception:
        pass

    await _add_system_interpreters_remote(items, seen, backend)

    if configured and str(configured).strip():
        raw = str(configured).strip()
        if raw not in seen:
            _append_interpreter_item(items, seen, path=raw, kind="custom")

    return items


def _configured_interpreter(workspace_root: str | None, configured: str | None) -> str:
    if configured is not None:
        text = configured.strip()
        return text
    # Workspace .code-agent/config.yaml wins over auto-discovery and global setting.
    if workspace_root:
        ws_val = get_workspace_setting(workspace_root, "python.interpreter")
        if ws_val is not None and str(ws_val).strip():
            return str(ws_val).strip()
    discovered = discover_workspace_venv(workspace_root)
    if discovered:
        return discovered
    return str(settings.get("python.interpreter") or "").strip()


def resolve_python_env(
    *,
    workspace_root: str | None = None,
    configured: str | None = None,
) -> PythonEnv:
    """Build PATH / VIRTUAL_ENV from ``python.interpreter`` or auto-discovered venv.

    ``configured`` may be:
    - path to a python binary (…/bin/python, …/Scripts/python.exe)
    - path to a venv directory (.venv)
    - relative to workspace root

    Resolution order: explicit ``configured`` → workspace config → auto-discover
    ``.venv`` / ``venv`` in the workspace → global user setting.
    Relative paths that are missing locally still soft-resolve so SSH terminals can
    ``source .venv/bin/activate``.
    """
    raw = _configured_interpreter(workspace_root, configured)
    if not raw:
        return PythonEnv()

    path = _resolve_path(raw, workspace_root)
    python: Path | None = None
    venv_root: Path | None = None
    soft = False

    if path.is_dir():
        # Treat as venv root
        if sys.platform == "win32":
            candidates = [path / "Scripts" / "python.exe", path / "python.exe"]
        else:
            candidates = [path / "bin" / "python3", path / "bin" / "python"]
        for cand in candidates:
            if cand.is_file():
                python = cand
                venv_root = path
                break
        if python is None:
            # Directory without python — still put it on PATH if bin/Scripts exists
            bin_dir = path / ("Scripts" if sys.platform == "win32" else "bin")
            if bin_dir.is_dir():
                venv_root = path
            else:
                soft = True
                venv_root = path
                python = candidates[0]
    elif path.exists() or _is_exe(path):
        python = path
        venv_root = _venv_root_from_python(path)
    elif _looks_like_python_binary(path.name):
        soft = True
        python = path
        venv_root = _venv_root_from_python(path)
    else:
        # Relative dir that does not exist locally (e.g. SSH .venv)
        soft = True
        venv_root = path
        if sys.platform == "win32":
            python = path / "Scripts" / "python.exe"
        else:
            python = path / "bin" / "python3"

    if python is None and venv_root is None:
        return PythonEnv()

    env: dict[str, str] = {}
    bin_dir: Path | None = None
    if venv_root is not None:
        bin_dir = venv_root / ("Scripts" if sys.platform == "win32" else "bin")
        env["VIRTUAL_ENV"] = str(venv_root)
        # Clear PYTHONHOME so the venv is not shadowed by embeddable / system home.
        env["PYTHONHOME"] = ""
        prompt = venv_root.name or ".venv"
        env["VIRTUAL_ENV_PROMPT"] = prompt
    elif python is not None:
        bin_dir = python.parent

    # Only prepend PATH when the bin dir exists locally (skip soft/SSH missing paths).
    if bin_dir is not None and bin_dir.is_dir():
        old = os.environ.get("PATH", "")
        env["PATH"] = f"{bin_dir}{os.pathsep}{old}" if old else str(bin_dir)
    elif bin_dir is not None and not soft:
        old = os.environ.get("PATH", "")
        env["PATH"] = f"{bin_dir}{os.pathsep}{old}" if old else str(bin_dir)

    # Soft resolve without local bin: keep VIRTUAL_ENV for activate script / SSH export.
    if soft and "VIRTUAL_ENV" not in env and "PATH" not in env:
        return PythonEnv()

    label = _label_for_venv(venv_root, python)
    return PythonEnv(
        python=str(python) if python else None,
        venv_root=str(venv_root) if venv_root else None,
        label=label,
        env=env,
    )


def merge_python_env(base: dict[str, str] | None, pyenv: PythonEnv | None) -> dict[str, str]:
    """Copy ``base`` (default ``os.environ``) and apply interpreter env."""
    out = dict(base if base is not None else os.environ)
    if not pyenv or not pyenv.env:
        return out
    for key, value in pyenv.env.items():
        if key == "PYTHONHOME" and value == "":
            out.pop("PYTHONHOME", None)
            continue
        out[key] = value
    return out


def shell_export_prefix(pyenv: PythonEnv | None, *, windows: bool = False) -> str:
    """Shell snippet that activates the interpreter (for SSH / cmd wrappers)."""
    if not pyenv or not pyenv.env:
        return ""
    if windows:
        parts: list[str] = []
        if pyenv.env.get("VIRTUAL_ENV"):
            parts.append(f'set "VIRTUAL_ENV={pyenv.env["VIRTUAL_ENV"]}"')
        if pyenv.env.get("PATH"):
            parts.append(f'set "PATH={pyenv.env["PATH"]}"')
        parts.append('set "PYTHONHOME="')
        return "& ".join(parts) + " & " if parts else ""
    parts = []
    if pyenv.env.get("VIRTUAL_ENV"):
        parts.append(f'export VIRTUAL_ENV={_sh_quote(pyenv.env["VIRTUAL_ENV"])}')
    if pyenv.env.get("VIRTUAL_ENV_PROMPT"):
        parts.append(f'export VIRTUAL_ENV_PROMPT={_sh_quote(pyenv.env["VIRTUAL_ENV_PROMPT"])}')
    if pyenv.env.get("PATH"):
        parts.append(f'export PATH={_sh_quote(pyenv.env["PATH"])}')
    parts.append("unset PYTHONHOME")
    return " && ".join(parts) + " && " if parts else ""


def activation_shell_command(
    pyenv: PythonEnv | None,
    *,
    windows: bool = False,
    shell: str | None = None,
    cwd: str | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return a line that sources the venv activate script (for interactive terminals)."""
    if not pyenv or not pyenv.venv_root:
        return None
    root = Path(pyenv.venv_root)
    shell_l = (shell or "").lower()

    def _rel_or_abs(target: Path) -> str:
        for base in (cwd, workspace_root):
            if not base:
                continue
            try:
                rel = target.resolve().relative_to(Path(base).resolve())
                return str(rel).replace("\\", "/")
            except (ValueError, OSError):
                continue
        # Prefer short relative form when soft-resolved under workspace.
        try:
            if workspace_root:
                rel = root.relative_to(Path(workspace_root))
                leaf = (rel / target.relative_to(root)).as_posix()
                return leaf
        except (ValueError, OSError):
            pass
        return str(target).replace("\\", "/")

    if windows:
        if "powershell" in shell_l or "pwsh" in shell_l:
            ps1 = root / "Scripts" / "Activate.ps1"
            return f'& "{_rel_or_abs(ps1)}"'
        bat = root / "Scripts" / "activate.bat"
        return f'call "{_rel_or_abs(bat)}"'
    activate = root / "bin" / "activate"
    rel = _rel_or_abs(activate)
    return f"source {_sh_quote(rel)}"


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def terminal_title_with_env(base: str, pyenv: PythonEnv | None) -> str:
    """Prefix terminal tab title with env label (e.g. ``.venv · Terminal``)."""
    label = (pyenv.label if pyenv else None) or None
    if not label:
        return base
    if base.startswith(f"{label} · ") or base.startswith(f"{label} "):
        return base
    return f"{label} · {base}"
