from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from code_agent.config import REPO_ROOT, ensure_user_config, settings
from code_agent.runtime.profile import runtime_profile

RUN_DIR = Path.home() / ".code-agent" / "run"
PID_DIR = RUN_DIR / "pids"
LOG_DIR = RUN_DIR / "logs"

WEB_DIR = REPO_ROOT / "apps" / "web"
API_DIR = REPO_ROOT / "apps" / "api"


def _ports() -> dict[str, int]:
    return {
        "api": int(settings.get("server.port") or 4060),
        "web": int(settings.get("server.dev_ui_port") or 4061),
        "terminal": int(settings.get("runtime.terminal.port") or 4062),
        "preview": int(settings.get("runtime.preview.port") or 4063),
        "worker": int(settings.get("runtime.agent_worker.port") or 4064),
    }


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _is_port_listening(port: int) -> bool:
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.stdout.strip():
            return True
    except FileNotFoundError:
        pass
    try:
        out = subprocess.run(
            ["ss", "-ltn", f"sport = :{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f":{port}" in out.stdout
    except FileNotFoundError:
        return False


def _wait_for_port_free(port: int, *, attempts: int = 25) -> bool:
    for _ in range(attempts):
        if not _is_port_listening(port):
            return True
        time.sleep(0.2)
    return False


def _ensure_ports_free(ports: dict[str, int]) -> None:
    for port in ports.values():
        if _is_port_listening(port):
            _kill_port(port)
        _wait_for_port_free(port)


def _wait_for_port(port: int, *, attempts: int = 30) -> bool:
    for _ in range(attempts):
        if _is_port_listening(port):
            return True
        time.sleep(0.2)
    return False


def _legacy_dev_stop() -> None:
    """Stop processes started by the old repo-local .dev/pids layout."""
    pid_dir = REPO_ROOT / ".dev" / "pids"
    if not pid_dir.is_dir():
        return
    for pidfile in pid_dir.glob("*.pid"):
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except ValueError:
            pidfile.unlink(missing_ok=True)
            continue
        if _pid_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        pidfile.unlink(missing_ok=True)


def _kill_port(port: int) -> None:
    killed = False
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
    except FileNotFoundError:
        pids = []
    if not pids:
        try:
            out = subprocess.run(
                ["ss", "-ltnp", f"sport = :{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = [int(m) for m in re.findall(r"pid=(\d+)", out.stdout)]
        except FileNotFoundError:
            pids = []
    if not pids:
        return
    print(f"→ freeing port {port}")
    killed = True
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    if killed:
        time.sleep(0.3)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _clear_stale_pidfiles() -> None:
    if not PID_DIR.is_dir():
        return
    for pidfile in PID_DIR.glob("*.pid"):
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except ValueError:
            pidfile.unlink(missing_ok=True)
            continue
        if not _pid_alive(pid):
            pidfile.unlink(missing_ok=True)


def _stop_pidfile(name: str) -> None:
    pidfile = PID_DIR / f"{name}.pid"
    if not pidfile.is_file():
        return
    try:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
    except ValueError:
        pidfile.unlink(missing_ok=True)
        return
    if _pid_alive(pid):
        print(f"→ stopping {name} (pid {pid})")
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    pidfile.unlink(missing_ok=True)


def stop(*, quiet: bool = False) -> None:
    if not quiet:
        print("Code Agent stop")
    _clear_stale_pidfiles()
    _legacy_dev_stop()
    if PID_DIR.is_dir():
        for pidfile in list(PID_DIR.glob("*.pid")):
            _stop_pidfile(pidfile.stem)
    ports = _ports()
    for port in (ports["web"], ports["api"], ports["terminal"], ports["preview"], ports["worker"]):
        _kill_port(port)
    _ensure_ports_free(ports)
    if not quiet:
        print("✓ stopped")


def _start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    port: int | None = None,
) -> None:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pidfile = PID_DIR / f"{name}.pid"
    if pidfile.is_file():
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
        if pid and _pid_alive(pid):
            print(f"✓ {name} already running (pid {pid})")
            return

    log_path = LOG_DIR / f"{name}.log"
    log_path.write_text("", encoding="utf-8")
    print(f"→ starting {name} …")
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    with log_path.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=proc_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pidfile.write_text(str(proc.pid), encoding="utf-8")

    if port is not None:
        if _wait_for_port(port):
            print(f"✓ {name} listening on :{port} (pid {proc.pid})  log: {log_path}")
            return
    elif _pid_alive(proc.pid):
        time.sleep(0.8)
        if _pid_alive(proc.pid):
            print(f"✓ {name} pid {proc.pid}  log: {log_path}")
            return

    print(f"✗ {name} failed — see {log_path}")
    tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
    for line in tail:
        print(f"  {line}")
    if port is not None and any("already in use" in line for line in tail):
        print(f"  hint: port {port} is occupied — run `code-agent stop` first")
    pidfile.unlink(missing_ok=True)
    raise SystemExit(1)


def _python_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "code_agent", *args]


def _ensure_frontend_built(*, force: bool = False) -> None:
    dist = WEB_DIR / "dist" / "index.html"
    if dist.is_file() and not force:
        return
    if not (WEB_DIR / "package.json").is_file():
        raise SystemExit(f"Frontend not found: {WEB_DIR}")
    print("→ building frontend …")
    subprocess.run(["npm", "run", "build"], cwd=str(WEB_DIR), check=True)


def _service_env(*, split: bool, ports: dict[str, int]) -> dict[str, str]:
    env = {
        "CODE_AGENT_PORT": str(ports["api"]),
        "CODE_AGENT_DEV_UI_PORT": str(ports["web"]),
        "CODE_AGENT_TERMINAL_PORT": str(ports["terminal"]),
        "CODE_AGENT_PREVIEW_PORT": str(ports["preview"]),
    }
    if split:
        env["CODE_AGENT_RUNTIME_PROFILE"] = "split"
    return env


def start(*, production: bool = False, build: bool = False) -> None:
    ensure_user_config(quiet=True)
    settings.reload()
    profile = runtime_profile()
    split = profile == "split"
    ports = _ports()
    mode = "production" if production else "development"
    print(f"Code Agent start ({mode}, profile={profile})")
    stop(quiet=True)
    _ensure_ports_free(ports)

    if production:
        _ensure_frontend_built(force=build)
        if split:
            _start_process("api", _python_cmd("api"), cwd=API_DIR, port=ports["api"])
            _start_process("worker", _python_cmd("worker"), cwd=API_DIR)
            _start_process(
                "terminal",
                _python_cmd("terminal"),
                cwd=API_DIR,
                env={"CODE_AGENT_RUNTIME_PROFILE": "split"},
                port=ports["terminal"],
            )
            _start_process(
                "preview",
                _python_cmd("preview"),
                cwd=API_DIR,
                env={"CODE_AGENT_RUNTIME_PROFILE": "split"},
                port=ports["preview"],
            )
            print("")
            print(f"Open:   http://127.0.0.1:{ports['api']}")
            print(f"API:    http://127.0.0.1:{ports['api']}/api/health")
            print(f"Terminal: http://127.0.0.1:{ports['terminal']}")
            print(f"Preview:  http://127.0.0.1:{ports['preview']}")
        else:
            _start_process("api", _python_cmd("monolith"), cwd=API_DIR, port=ports["api"])
            print("")
            print(f"Open: http://127.0.0.1:{ports['api']}")
    else:
        env = _service_env(split=split, ports=ports)
        if split:
            _start_process("api", _python_cmd("api"), cwd=API_DIR, port=ports["api"])
            _start_process("worker", _python_cmd("worker"), cwd=API_DIR)
            _start_process(
                "terminal",
                _python_cmd("terminal"),
                cwd=API_DIR,
                env={"CODE_AGENT_RUNTIME_PROFILE": "split"},
                port=ports["terminal"],
            )
            _start_process(
                "preview",
                _python_cmd("preview"),
                cwd=API_DIR,
                env={"CODE_AGENT_RUNTIME_PROFILE": "split"},
                port=ports["preview"],
            )
            _start_process(
                "web",
                ["npm", "run", "dev"],
                cwd=WEB_DIR,
                env=env,
                port=ports["web"],
            )
        else:
            _start_process("api", _python_cmd("monolith"), cwd=API_DIR, port=ports["api"])
            _start_process(
                "web",
                ["npm", "run", "dev"],
                cwd=WEB_DIR,
                env=env,
                port=ports["web"],
            )
        print("")
        print(f"API:  http://127.0.0.1:{ports['api']}")
        print(f"Web:  http://127.0.0.1:{ports['web']}")

    print(f"Logs: {LOG_DIR}")
    print("Stop: code-agent stop")


def restart(*, production: bool = False, build: bool = False) -> None:
    stop()
    start(production=production, build=build)


def status() -> None:
    ensure_user_config(quiet=True)
    settings.reload()
    ports = _ports()
    profile = runtime_profile()
    print(f"profile={profile}")
    if PID_DIR.is_dir():
        found = False
        for pidfile in sorted(PID_DIR.glob("*.pid")):
            found = True
            name = pidfile.stem
            try:
                pid = int(pidfile.read_text(encoding="utf-8").strip())
            except ValueError:
                print(f"  {name}: invalid pid file")
                continue
            alive = _pid_alive(pid)
            print(f"  {name}: pid {pid} ({'running' if alive else 'dead'})")
        if not found:
            print("  (no managed processes)")
    else:
        print("  (no managed processes)")
    for label, port in ports.items():
        listening = _is_port_listening(port)
        print(f"  port {port} ({label}): {'listening' if listening else 'free'}")
