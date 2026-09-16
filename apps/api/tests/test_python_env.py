from __future__ import annotations

import os
from pathlib import Path

from code_agent.runtime.python_env import (
    activation_shell_command,
    discover_python_interpreters_local,
    discover_workspace_venv,
    merge_python_env,
    resolve_python_env,
    shell_export_prefix,
    terminal_title_with_env,
)


def test_resolve_venv_dir(tmp_path: Path, monkeypatch):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: str(venv) if key == "python.interpreter" else default,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    env = resolve_python_env(workspace_root=str(tmp_path))
    assert env.active
    assert env.label == ".venv"
    assert env.venv_root == str(venv.resolve())
    assert env.python and env.python.endswith("python")
    assert str(bin_dir.resolve()) in env.env["PATH"].split(os.pathsep)
    assert env.env["VIRTUAL_ENV"] == str(venv.resolve())
    cmd = activation_shell_command(env, cwd=str(tmp_path), workspace_root=str(tmp_path))
    assert cmd == "source '.venv/bin/activate'"


def test_resolve_relative_python_binary(tmp_path: Path, monkeypatch):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python3"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: ".venv/bin/python3" if key == "python.interpreter" else default,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    env = resolve_python_env(workspace_root=str(tmp_path))
    assert env.label == ".venv"
    assert Path(env.python).resolve() == python.resolve()


def test_workspace_config_overrides_user(tmp_path: Path, monkeypatch):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    cfg_dir = tmp_path / ".code-agent"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("python:\n  interpreter: .venv\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: "/other/python" if key == "python.interpreter" else default,
    )
    env = resolve_python_env(workspace_root=str(tmp_path))
    assert env.label == ".venv"
    assert Path(env.python).resolve() == python.resolve()


def test_merge_and_export(tmp_path: Path):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("x", encoding="utf-8")
    python.chmod(0o755)
    env = resolve_python_env(workspace_root=str(tmp_path), configured=str(venv))
    merged = merge_python_env({"PATH": "/usr/bin", "PYTHONHOME": "/old"}, env)
    assert merged["VIRTUAL_ENV"] == str(venv.resolve())
    assert "PYTHONHOME" not in merged
    assert merged["PATH"].startswith(str(bin_dir.resolve()))
    prefix = shell_export_prefix(env)
    assert "VIRTUAL_ENV=" in prefix
    assert "unset PYTHONHOME" in prefix
    assert terminal_title_with_env("Terminal", env) == ".venv · Terminal"


def test_empty_setting(monkeypatch):
    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: "" if key == "python.interpreter" else default,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    env = resolve_python_env(workspace_root="/tmp")
    assert not env.active
    assert terminal_title_with_env("Terminal", env) == "Terminal"


def test_auto_discover_venv(tmp_path: Path, monkeypatch):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: "" if key == "python.interpreter" else default,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    env = resolve_python_env(workspace_root=str(tmp_path))
    assert env.active
    assert env.label == ".venv"
    cmd = activation_shell_command(env, cwd=str(tmp_path), workspace_root=str(tmp_path))
    assert cmd == "source '.venv/bin/activate'"


def test_discover_python_interpreters_local(tmp_path: Path, monkeypatch):
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env._read_python_version",
        lambda exe: "Python 3.11.9",
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env._add_system_interpreters",
        lambda items, seen: None,
    )
    items = discover_python_interpreters_local(str(tmp_path))
    assert len(items) == 1
    assert items[0]["path"] == ".venv"
    assert "3.11.9" in items[0]["label"]


def test_discover_includes_system_python(tmp_path: Path, monkeypatch):
    system_py = tmp_path / "bin" / "python3"
    system_py.parent.mkdir(parents=True)
    system_py.write_text("#!/bin/sh\n", encoding="utf-8")
    system_py.chmod(0o755)

    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env._collect_system_python_executables",
        lambda: [system_py],
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env._read_python_version",
        lambda exe: "Python 3.12.1",
    )
    items = discover_python_interpreters_local(str(tmp_path))
    assert any(i["kind"] == "system" and i["path"] == str(system_py.resolve()) for i in items)


def test_auto_discover_prefers_dot_venv_over_venv(tmp_path: Path, monkeypatch):
    for name in (".venv", "venv"):
        root = tmp_path / name
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True)
        py = bin_dir / "python"
        py.write_text("#!/bin/sh\n", encoding="utf-8")
        py.chmod(0o755)
        (root / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    monkeypatch.setattr(
        "code_agent.runtime.python_env.settings.get",
        lambda key, default=None: "" if key == "python.interpreter" else default,
    )
    monkeypatch.setattr(
        "code_agent.runtime.python_env.get_workspace_setting",
        lambda *args, **kwargs: None,
    )
    assert discover_workspace_venv(str(tmp_path)) == ".venv"
