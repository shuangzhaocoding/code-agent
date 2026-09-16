"""Workspace filesystem watch (VS Code-style) with SSE fan-out.

Local workspaces use ``watchfiles`` (inotify/FSEvents/ReadDirectoryChanges).

SSH workspaces (in order):
1. Remote ``inotifywait`` when available (true remote watch, like VS Code remote).
2. If missing, try to install ``inotify-tools`` non-interactively on the host.
3. Otherwise poll a filesystem mtime fingerprint (does **not** require git) and
   surface an install hint to the UI.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from code_agent.db.models import Workspace
from code_agent.tools.paths import TREE_IGNORES, matches_ignore
from code_agent.workspace.backend import get_workspace_backend, workspace_is_ssh

logger = logging.getLogger(__name__)

# Extra noise dirs common in projects (tree already hides some via config).
_WATCH_EXTRA_IGNORES = [
    "node_modules",
    "bower_components",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
    ".idea",
    ".vscode",
]

_DEBOUNCE_MS = 400
_SSH_POLL_SEC = 8.0
_SSH_INOTIFY_DEBOUNCE_SEC = 0.45
_SSH_INSTALL_TIMEOUT_SEC = 240
_MAX_PATHS_PER_EVENT = 40
_SSH_FIND_MAXDEPTH = 4
_SSH_FIND_MAX_LINES = 8000

# Multi-strategy install: try every common package manager, as root and with
# passwordless ``sudo -n``. Password prompts are never used (would hang SSH).
_SSH_INSTALL_INOTIFY_SCRIPT = r"""
set +e
if command -v inotifywait >/dev/null 2>&1; then
  echo OK_ALREADY
  exit 0
fi
os=$(uname -s 2>/dev/null || echo unknown)
case "$os" in
  Linux|linux) ;;
  *)
    echo "UNSUPPORTED_OS:$os"
    exit 2
    ;;
esac

run_as_admin() {
  # 1) already root
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return $?
  fi
  # 2) plain command (some images allow apt without sudo for the login user)
  "$@"
  rc=$?
  if [ $rc -eq 0 ]; then
    return 0
  fi
  # 3) passwordless sudo
  if command -v sudo >/dev/null 2>&1; then
    sudo -n "$@"
    return $?
  fi
  return $rc
}

try_cmd() {
  label="$1"
  shift
  echo "TRY:$label"
  run_as_admin "$@"
  rc=$?
  if command -v inotifywait >/dev/null 2>&1; then
    echo "OK:$label"
    exit 0
  fi
  echo "FAIL:$label:rc=$rc"
  return $rc
}

# apt / apt-get
if command -v apt-get >/dev/null 2>&1 || command -v apt >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  APT_BIN=$(command -v apt-get || command -v apt)
  try_cmd apt-update-install bash -c "$APT_BIN update -qq && $APT_BIN install -y -qq inotify-tools"
  try_cmd apt-install bash -c "$APT_BIN install -y -qq inotify-tools"
  try_cmd apt-install-verbose bash -c "$APT_BIN install -y inotify-tools"
fi

# dnf / microdnf / yum
if command -v dnf >/dev/null 2>&1; then
  try_cmd dnf-install dnf install -y inotify-tools
fi
if command -v microdnf >/dev/null 2>&1; then
  try_cmd microdnf-install microdnf install -y inotify-tools
fi
if command -v yum >/dev/null 2>&1; then
  try_cmd yum-install yum install -y inotify-tools
fi

# Alpine
if command -v apk >/dev/null 2>&1; then
  try_cmd apk-install apk add --no-cache inotify-tools
  try_cmd apk-install-update bash -c "apk update && apk add --no-cache inotify-tools"
fi

# Arch
if command -v pacman >/dev/null 2>&1; then
  try_cmd pacman-install pacman -Sy --noconfirm inotify-tools
fi

# openSUSE
if command -v zypper >/dev/null 2>&1; then
  try_cmd zypper-install zypper --non-interactive install -y inotify-tools
fi

# Extra: some distros ship the binary under a different package name path after
# a partial install — rehash and recheck.
hash -r 2>/dev/null
if command -v inotifywait >/dev/null 2>&1; then
  echo OK_INSTALLED
  exit 0
fi

echo INSTALL_FAILED
echo HINT:need_root_or_passwordless_sudo
exit 1
""".strip()

# Fallback one-liners if the bundled script cannot run (no bash / no base64).
_SSH_INSTALL_FALLBACK_CMDS: tuple[str, ...] = (
    "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq inotify-tools",
    "DEBIAN_FRONTEND=noninteractive sudo -n apt-get update -qq && DEBIAN_FRONTEND=noninteractive sudo -n apt-get install -y -qq inotify-tools",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y inotify-tools",
    "DEBIAN_FRONTEND=noninteractive sudo -n apt-get install -y inotify-tools",
    "DEBIAN_FRONTEND=noninteractive apt install -y inotify-tools",
    "DEBIAN_FRONTEND=noninteractive sudo -n apt install -y inotify-tools",
    "dnf install -y inotify-tools",
    "sudo -n dnf install -y inotify-tools",
    "microdnf install -y inotify-tools",
    "sudo -n microdnf install -y inotify-tools",
    "yum install -y inotify-tools",
    "sudo -n yum install -y inotify-tools",
    "apk add --no-cache inotify-tools",
    "sudo -n apk add --no-cache inotify-tools",
    "pacman -Sy --noconfirm inotify-tools",
    "sudo -n pacman -Sy --noconfirm inotify-tools",
    "zypper --non-interactive install -y inotify-tools",
    "sudo -n zypper --non-interactive install -y inotify-tools",
)

_PRUNE_EXPR = " -o ".join(
    f"-name {shlex.quote(n)}"
    for n in (".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build", ".next", ".idea")
)


def _watch_ignore_patterns() -> list[str]:
    return list(dict.fromkeys([*TREE_IGNORES, *_WATCH_EXTRA_IGNORES, ".git"]))


def _rel_from_root(root: Path, absolute: str | Path) -> str | None:
    try:
        rel = Path(absolute).resolve().relative_to(root.resolve())
        return rel.as_posix()
    except (ValueError, OSError):
        return None


def _should_ignore_rel(rel: str) -> bool:
    text = (rel or "").replace("\\", "/").strip("/")
    if not text:
        return False
    if text == ".git" or text.startswith(".git/"):
        return True
    return matches_ignore(text, _watch_ignore_patterns())


@dataclass
class _WorkspaceWatch:
    workspace_id: str
    root_path: str
    is_ssh: bool
    queues: list[asyncio.Queue] = field(default_factory=list)
    task: asyncio.Task | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    mode: str = "watch"
    ready_extra: dict[str, Any] = field(default_factory=dict)

    def subscriber_count(self) -> int:
        return len(self.queues)


class WorkspaceWatchHub:
    def __init__(self) -> None:
        self._by_id: dict[str, _WorkspaceWatch] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, ws: Workspace) -> AsyncIterator[dict[str, Any]]:
        """Yield workspace change events until the consumer cancels."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        async with self._lock:
            entry = self._by_id.get(str(ws.id))
            if entry is None:
                entry = _WorkspaceWatch(
                    workspace_id=str(ws.id),
                    root_path=ws.root_path,
                    is_ssh=workspace_is_ssh(ws),
                    mode="ssh-poll" if workspace_is_ssh(ws) else "watch",
                )
                self._by_id[str(ws.id)] = entry
            entry.queues.append(queue)
            if entry.task is None or entry.task.done():
                entry.stop = asyncio.Event()
                entry.task = asyncio.create_task(
                    self._run_watch(entry),
                    name=f"ws-watch-{entry.workspace_id}",
                )

        try:
            yield {
                "type": "fs.ready",
                "workspace_id": str(ws.id),
                "mode": entry.mode,
                **entry.ready_extra,
            }
            # Late subscribers while poll is running: ask poll loop to re-check inotify
            # (user may have installed tools after the first failed attempt).
            if entry.is_ssh and entry.mode == "ssh-poll" and entry.task and not entry.task.done():
                entry.ready_extra["reprobe_inotify"] = True
            while True:
                event = await queue.get()
                yield event
        finally:
            await self._unsubscribe(str(ws.id), queue)

    async def _unsubscribe(self, workspace_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            entry = self._by_id.get(workspace_id)
            if entry is None:
                return
            if queue in entry.queues:
                entry.queues.remove(queue)
            if entry.queues:
                return
            entry.stop.set()
            task = entry.task
            entry.task = None
            self._by_id.pop(workspace_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    def _broadcast(self, entry: _WorkspaceWatch, event: dict[str, Any]) -> None:
        dead: list[asyncio.Queue] = []
        for q in list(entry.queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in entry.queues:
                entry.queues.remove(q)

    def _emit_ready(self, entry: _WorkspaceWatch, **extra: Any) -> None:
        merged = {**entry.ready_extra}
        for key, value in extra.items():
            if value is not None:
                merged[key] = value
        entry.ready_extra = merged
        self._broadcast(
            entry,
            {
                "type": "fs.ready",
                "workspace_id": entry.workspace_id,
                "mode": entry.mode,
                **entry.ready_extra,
            },
        )

    async def _run_watch(self, entry: _WorkspaceWatch) -> None:
        try:
            if entry.is_ssh:
                await self._watch_ssh(entry)
            else:
                await self._watch_local(entry)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("workspace watch failed id=%s", entry.workspace_id)
            self._broadcast(
                entry,
                {
                    "type": "fs.error",
                    "workspace_id": entry.workspace_id,
                    "message": "workspace watch stopped",
                },
            )

    async def _watch_local(self, entry: _WorkspaceWatch) -> None:
        try:
            from watchfiles import Change, awatch
        except ImportError as exc:
            raise RuntimeError("watchfiles is required for local workspace watching") from exc

        root = Path(entry.root_path).expanduser()
        if not root.is_dir():
            self._broadcast(
                entry,
                {
                    "type": "fs.error",
                    "workspace_id": entry.workspace_id,
                    "message": "workspace root missing",
                },
            )
            return

        def watch_filter(change: Change, path: str) -> bool:
            rel = _rel_from_root(root, path)
            if rel is None:
                return False
            return not _should_ignore_rel(rel)

        async for changes in awatch(
            str(root),
            stop_event=entry.stop,
            watch_filter=watch_filter,
            debounce=_DEBOUNCE_MS,
            step=50,
        ):
            if entry.stop.is_set():
                break
            if not changes:
                continue
            pending: dict[str, str] = {}
            for change, abs_path in changes:
                rel = _rel_from_root(root, abs_path)
                if rel is None or _should_ignore_rel(rel):
                    continue
                kind = {
                    Change.added: "added",
                    Change.modified: "modified",
                    Change.deleted: "deleted",
                }.get(change, "modified")
                pending[rel] = kind
            if pending:
                self._emit_paths(entry, pending)

    def _emit_paths(self, entry: _WorkspaceWatch, pending: dict[str, str]) -> None:
        items = list(pending.items())[:_MAX_PATHS_PER_EVENT]
        paths = [p for p, _ in items]
        kinds = [k for _, k in items]
        self._broadcast(
            entry,
            {
                "type": "fs.changed",
                "workspace_id": entry.workspace_id,
                "paths": paths,
                "kinds": kinds,
                "truncated": len(pending) > len(items),
            },
        )

    def _emit_ssh_changed(self, entry: _WorkspaceWatch, *, reason: str, paths: list[str] | None = None) -> None:
        self._broadcast(
            entry,
            {
                "type": "fs.changed",
                "workspace_id": entry.workspace_id,
                "paths": paths or [],
                "kinds": [],
                "reason": reason,
            },
        )

    async def _watch_ssh(self, entry: _WorkspaceWatch) -> None:
        """Prefer remote inotifywait (install if needed); else poll and keep re-probing."""
        while not entry.stop.is_set():
            if await self._ssh_try_inotify(entry):
                # Stream ended (process exit / network). Retry instead of dying silent.
                try:
                    await asyncio.wait_for(entry.stop.wait(), timeout=2.0)
                except TimeoutError:
                    pass
                continue

            entry.mode = "ssh-poll"
            self._emit_ready(
                entry,
                reason="inotify_unavailable",
                hint_code="install_inotify_tools",
                install_attempted=bool(entry.ready_extra.get("install_attempted")),
                install_ok=False,
            )
            # Returns when stop set, or when inotify became available (upgrade).
            upgraded = await self._watch_ssh_poll(entry)
            if entry.stop.is_set():
                return
            if upgraded:
                # Clear stale hint before switching to realtime watch.
                entry.ready_extra.pop("hint_code", None)
                entry.ready_extra.pop("reason", None)
                continue
            return

    async def _ssh_has_inotifywait(self, backend: Any) -> bool:
        # Non-login SSH shells often have a slim PATH — check common locations too.
        code, which_out, _ = await backend.run_command(
            "export PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH\"; "
            "(command -v inotifywait) || "
            "(test -x /usr/bin/inotifywait && echo /usr/bin/inotifywait) || "
            "(test -x /usr/local/bin/inotifywait && echo /usr/local/bin/inotifywait)",
            cwd=".",
            timeout=10,
        )
        return code == 0 and bool((which_out or "").strip())

    async def _ssh_probe_inotify_available(self, entry: _WorkspaceWatch) -> bool:
        """Lightweight check (no install) used while polling."""
        ws = await Workspace.get_or_none(id=entry.workspace_id)
        if ws is None:
            return False
        backend = await get_workspace_backend(ws)
        try:
            return await self._ssh_has_inotifywait(backend)
        except Exception:
            return False
        finally:
            try:
                await backend.close()
            except Exception:
                pass

    async def _ssh_ensure_inotifywait(self, entry: _WorkspaceWatch, backend: Any) -> bool:
        """Return True if inotifywait is available (already present or after install)."""
        if await self._ssh_has_inotifywait(backend):
            return True

        self._broadcast(
            entry,
            {
                "type": "fs.progress",
                "workspace_id": entry.workspace_id,
                "phase": "installing_inotify",
            },
        )
        entry.ready_extra["install_attempted"] = True
        logger.info("SSH ws=%s: inotifywait missing, attempting install", entry.workspace_id)

        details: list[str] = []

        # Prefer base64|bash so newlines survive asyncssh wrapping.
        b64 = base64.b64encode(_SSH_INSTALL_INOTIFY_SCRIPT.encode("utf-8")).decode("ascii")
        primary = f"printf '%s' {shlex.quote(b64)} | base64 -d | bash"
        try:
            code, out, err = await backend.run_command(
                primary, cwd=".", timeout=_SSH_INSTALL_TIMEOUT_SEC
            )
            details.append(f"script:exit={code}\n{(out or '')}\n{(err or '')}".strip())
        except Exception as exc:
            details.append(f"script:exc={exc}")
            code, out, err = 1, "", str(exc)

        if await self._ssh_has_inotifywait(backend):
            logger.info("SSH ws=%s: inotify-tools installed via script", entry.workspace_id)
            entry.ready_extra["install_ok"] = True
            entry.ready_extra["install_detail"] = details[-1][-400:]
            return True

        # Fallback: try discrete package-manager one-liners.
        for idx, cmd in enumerate(_SSH_INSTALL_FALLBACK_CMDS):
            if entry.stop.is_set():
                break
            try:
                code, out, err = await backend.run_command(cmd, cwd=".", timeout=90)
                details.append(
                    f"fallback[{idx}]:exit={code} cmd={cmd[:80]}\n{(out or '')[-120:]}\n{(err or '')[-120:]}".strip()
                )
            except Exception as exc:
                details.append(f"fallback[{idx}]:exc={exc}")
                continue
            if await self._ssh_has_inotifywait(backend):
                logger.info(
                    "SSH ws=%s: inotify-tools installed via fallback[%s]",
                    entry.workspace_id,
                    idx,
                )
                entry.ready_extra["install_ok"] = True
                entry.ready_extra["install_detail"] = details[-1][-400:]
                return True

        entry.ready_extra["install_detail"] = "\n---\n".join(details)[-800:]
        logger.warning(
            "SSH ws=%s: inotify install failed after %s attempts",
            entry.workspace_id,
            1 + len(_SSH_INSTALL_FALLBACK_CMDS),
        )
        return False

    async def _ssh_try_inotify(self, entry: _WorkspaceWatch) -> bool:
        """Stream remote inotifywait events. Returns False if unavailable."""
        ws = await Workspace.get_or_none(id=entry.workspace_id)
        if ws is None:
            return False
        backend = await get_workspace_backend(ws)
        try:
            if not await self._ssh_ensure_inotifywait(entry, backend):
                try:
                    await backend.close()
                except Exception:
                    pass
                return False

            # Use absolute path when possible — remote PATH may omit /usr/bin.
            code, which_out, _ = await backend.run_command(
                "export PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH\"; "
                "command -v inotifywait || true",
                cwd=".",
                timeout=10,
            )
            inotify_bin = (which_out or "").strip().splitlines()[-1].strip() if which_out else ""
            if not inotify_bin:
                inotify_bin = "inotifywait"

            # Exclude heavy / VCS dirs; still notice project file changes.
            exclude = r"(/\.(git|venv|idea|vscode|mypy_cache|pytest_cache|ruff_cache|tox|nox|next|nuxt|turbo)|/(node_modules|__pycache__|venv|dist|build|coverage)/)"
            root_q = shlex.quote(entry.root_path)
            bin_q = shlex.quote(inotify_bin)
            cmd = (
                f"cd {root_q} && {bin_q} -mrq "
                f"-e modify,create,delete,move,attrib "
                f"--exclude {shlex.quote(exclude)} "
                f"--format '%w%f' ."
            )
            conn = await backend._conn()  # type: ignore[attr-defined]
            process = await conn.create_process(cmd)
        except Exception:
            try:
                await backend.close()
            except Exception:
                pass
            return False

        entry.mode = "ssh-watch"
        # Drop poll hint so reconnecting clients stop showing the install toast.
        entry.ready_extra.pop("hint_code", None)
        entry.ready_extra.pop("reason", None)
        self._emit_ready(
            entry,
            install_attempted=bool(entry.ready_extra.get("install_attempted")),
            install_ok=bool(
                entry.ready_extra.get("install_ok", not entry.ready_extra.get("install_attempted"))
            ),
        )

        pending: dict[str, str] = {}
        flush_task: asyncio.Task | None = None

        async def flush_later() -> None:
            await asyncio.sleep(_SSH_INOTIFY_DEBOUNCE_SEC)
            if pending:
                batch = dict(pending)
                pending.clear()
                self._emit_paths(entry, batch)

        try:
            while not entry.stop.is_set():
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                except TimeoutError:
                    continue
                except Exception:
                    break
                if not line:
                    break
                text = line if isinstance(line, str) else line.decode("utf-8", errors="replace")
                abs_or_rel = text.strip()
                if not abs_or_rel:
                    continue
                # inotifywait %w%f is usually absolute under cwd or relative "./…"
                rel = abs_or_rel
                if rel.startswith("./"):
                    rel = rel[2:]
                root = entry.root_path.rstrip("/")
                if rel.startswith(root + "/"):
                    rel = rel[len(root) + 1 :]
                rel = rel.replace("\\", "/").lstrip("/")
                if not rel or _should_ignore_rel(rel):
                    continue
                pending[rel] = "modified"
                if flush_task is None or flush_task.done():
                    flush_task = asyncio.create_task(flush_later())
        finally:
            if flush_task and not flush_task.done():
                flush_task.cancel()
            if pending:
                self._emit_paths(entry, pending)
            try:
                process.terminate()
            except Exception:
                try:
                    process.close()
                except Exception:
                    pass
            try:
                await backend.close()
            except Exception:
                pass
        return True

    async def _watch_ssh_poll(self, entry: _WorkspaceWatch) -> bool:
        """Poll until stopped. Returns True if inotifywait appeared and we should upgrade."""
        last_fp: str | None = None
        ticks = 0
        while not entry.stop.is_set():
            ticks += 1
            # First tick + every ~24s, or when a new SSE subscriber asks for a re-probe.
            force = bool(entry.ready_extra.pop("reprobe_inotify", False))
            if force or ticks == 1 or ticks % 3 == 0:
                if await self._ssh_probe_inotify_available(entry):
                    logger.info(
                        "SSH ws=%s: inotifywait detected while polling — upgrading",
                        entry.workspace_id,
                    )
                    return True

            fp = await self._ssh_fingerprint(entry.workspace_id, entry.root_path)
            if fp is not None and fp != last_fp:
                if last_fp is not None:
                    self._emit_ssh_changed(entry, reason="ssh-poll")
                last_fp = fp
            try:
                await asyncio.wait_for(entry.stop.wait(), timeout=_SSH_POLL_SEC)
            except TimeoutError:
                continue
        return False

    async def _ssh_fingerprint(self, workspace_id: str, root_path: str) -> str | None:
        """Hash remote tree mtimes (+ git status when available). Works without git."""
        try:
            ws = await Workspace.get_or_none(id=workspace_id)
            if ws is None:
                return None
            backend = await get_workspace_backend(ws)
            try:
                root_q = shlex.quote(root_path)
                # Portable-ish: prefer GNU find -printf; fall back to stat lines.
                find_cmd = (
                    f"cd {root_q} && "
                    f"(find . -maxdepth {_SSH_FIND_MAXDEPTH} "
                    f"\\( {_PRUNE_EXPR} \\) -prune -o "
                    f"\\( -type f -o -type d \\) -printf '%T@ %p\\n' 2>/dev/null "
                    f"| head -n {_SSH_FIND_MAX_LINES}) "
                    f"|| (find . -maxdepth {_SSH_FIND_MAXDEPTH} "
                    f"\\( {_PRUNE_EXPR} \\) -prune -o "
                    f"\\( -type f -o -type d \\) -print 2>/dev/null "
                    f"| head -n {_SSH_FIND_MAX_LINES} | while IFS= read -r p; do "
                    f"stat -c '%Y %n' \"$p\" 2>/dev/null || stat -f '%m %N' \"$p\" 2>/dev/null; "
                    f"done)"
                )
                code, fs_out, _ = await backend.run_command(find_cmd, cwd=".", timeout=25)
                parts = [(fs_out or "").strip()]

                # Optional git layer — improves Git mark refresh when repo exists.
                git_code, git_out, _ = await backend.run_command(
                    "git rev-parse --is-inside-work-tree >/dev/null 2>&1 && "
                    "git status --porcelain=v1 -b --untracked-files=normal || true",
                    cwd=".",
                    timeout=20,
                )
                if git_code == 0 and (git_out or "").strip():
                    parts.append(git_out.strip())

                blob = "\n".join(parts)
                if not blob.strip() and code != 0:
                    return None
                return hashlib.sha1(blob.encode("utf-8", errors="replace")).hexdigest()
            finally:
                await backend.close()
        except Exception:
            return None


workspace_watch_hub = WorkspaceWatchHub()
