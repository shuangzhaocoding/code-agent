"""Workspace filesystem watch (VS Code-style) with SSE fan-out.

Local workspaces use ``watchfiles`` (inotify/FSEvents/ReadDirectoryChanges).

SSH workspaces (in order):
1. Remote ``inotifywait`` when available (true remote watch, like VS Code remote).
2. Otherwise poll a filesystem mtime fingerprint (does **not** require git).
   Git status is included in the fingerprint when the remote is a repo, so Git
   marks also refresh; non-git workspaces still detect create/modify/delete.
"""

from __future__ import annotations

import asyncio
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
_MAX_PATHS_PER_EVENT = 40
_SSH_FIND_MAXDEPTH = 4
_SSH_FIND_MAX_LINES = 8000

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
            }
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
        """Prefer remote inotifywait; else poll FS mtime fingerprint (+ git if present)."""
        if await self._ssh_try_inotify(entry):
            return
        entry.mode = "ssh-poll"
        self._broadcast(
            entry,
            {"type": "fs.ready", "workspace_id": entry.workspace_id, "mode": entry.mode},
        )
        await self._watch_ssh_poll(entry)

    async def _ssh_try_inotify(self, entry: _WorkspaceWatch) -> bool:
        """Stream remote inotifywait events. Returns False if unavailable."""
        ws = await Workspace.get_or_none(id=entry.workspace_id)
        if ws is None:
            return False
        backend = await get_workspace_backend(ws)
        try:
            code, which_out, _ = await backend.run_command(
                "command -v inotifywait", cwd=".", timeout=10
            )
            if code != 0 or not (which_out or "").strip():
                return False

            # Exclude heavy / VCS dirs; still notice project file changes.
            exclude = r"(/\.(git|venv|idea|vscode|mypy_cache|pytest_cache|ruff_cache|tox|nox|next|nuxt|turbo)|/(node_modules|__pycache__|venv|dist|build|coverage)/)"
            root_q = shlex.quote(entry.root_path)
            cmd = (
                f"cd {root_q} && inotifywait -mrq "
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
        self._broadcast(
            entry,
            {"type": "fs.ready", "workspace_id": entry.workspace_id, "mode": entry.mode},
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

    async def _watch_ssh_poll(self, entry: _WorkspaceWatch) -> None:
        last_fp: str | None = None
        while not entry.stop.is_set():
            fp = await self._ssh_fingerprint(entry.workspace_id, entry.root_path)
            if fp is not None and fp != last_fp:
                if last_fp is not None:
                    self._emit_ssh_changed(entry, reason="ssh-poll")
                last_fp = fp
            try:
                await asyncio.wait_for(entry.stop.wait(), timeout=_SSH_POLL_SEC)
            except TimeoutError:
                continue

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
