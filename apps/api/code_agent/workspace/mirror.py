from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from code_agent.config import settings
from code_agent.db.models import Workspace
from code_agent.workspace.backend import WorkspaceBackend, get_workspace_backend, workspace_is_ssh

log = logging.getLogger(__name__)

PLUGIN_REL = ".code-agent/plugins"
CONFIG_REL = ".code-agent/config.yaml"
SKILL_RELS = (
    ".code-agent/skills",
    ".agents/skills",
    ".cursor/skills",
)

_MAX_FILES = 400
_MAX_FILE_BYTES = 1_500_000
_MAX_DEPTH = 10

# Avoid wiping+re-downloading on every workspace switch / concurrent skills load.
_DEFAULT_TTL_SEC = 120.0
_synced_at: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


def mirror_root(workspace_id: str) -> Path:
    return Path(settings.data_dir) / "ssh-mirror" / str(workspace_id)


def clear_mirror(workspace_id: str) -> None:
    wid = str(workspace_id)
    _synced_at.pop(wid, None)
    root = mirror_root(wid)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def _ttl_sec() -> float:
    raw = settings.get("ssh.mirror_ttl_sec")
    try:
        return max(0.0, float(raw if raw is not None else _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SEC


def _lock_for(workspace_id: str) -> asyncio.Lock:
    wid = str(workspace_id)
    lock = _locks.get(wid)
    if lock is None:
        lock = asyncio.Lock()
        _locks[wid] = lock
    return lock


async def _sync_tree(
    backend: WorkspaceBackend,
    rel: str,
    dest: Path,
    *,
    depth: int,
    stats: dict[str, int],
) -> None:
    if depth > _MAX_DEPTH or stats["files"] >= _MAX_FILES:
        return
    try:
        if not await backend.is_dir(rel):
            return
    except Exception:
        return
    dest.mkdir(parents=True, exist_ok=True)
    try:
        items = await backend.list_dir(rel)
    except Exception as exc:
        log.debug("mirror list_dir %s failed: %s", rel, exc)
        return
    for item in items:
        if stats["files"] >= _MAX_FILES:
            return
        name = str(item.get("name") or "")
        if not name or name in {".", ".."}:
            continue
        child_rel = f"{rel.rstrip('/')}/{name}" if rel not in {"", "."} else name
        local = dest / name
        if item.get("is_dir"):
            await _sync_tree(backend, child_rel, local, depth=depth + 1, stats=stats)
            continue
        try:
            data = await backend.read_bytes(child_rel, max_bytes=_MAX_FILE_BYTES)
        except Exception as exc:
            log.debug("mirror read %s failed: %s", child_rel, exc)
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        stats["files"] += 1


async def _sync_file(backend: WorkspaceBackend, rel: str, dest: Path) -> bool:
    try:
        if not await backend.is_file(rel):
            return False
        data = await backend.read_bytes(rel, max_bytes=_MAX_FILE_BYTES)
    except Exception:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


async def sync_ssh_workspace_assets(ws: Workspace) -> Path:
    """Download remote plugins / skills / workspace config into a local mirror tree.

    Returns a fake local workspace root so existing Path-based loaders keep working:
    ``mirror/{id}/.code-agent/plugins``, ``.../skills``, etc.
    """
    if not workspace_is_ssh(ws):
        raise ValueError("sync_ssh_workspace_assets requires an SSH workspace")

    backend = await get_workspace_backend(ws)
    root = mirror_root(str(ws.id))
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    stats = {"files": 0}
    for rel in (PLUGIN_REL, *SKILL_RELS):
        await _sync_tree(backend, rel, root.joinpath(*rel.split("/")), depth=0, stats=stats)

    await _sync_file(backend, CONFIG_REL, root / ".code-agent" / "config.yaml")
    log.info("ssh mirror %s: synced %s files -> %s", ws.id, stats["files"], root)
    return root


def local_assets_root(ws: Workspace | dict[str, Any]) -> str | None:
    """Path to use for Path-based skills/plugins discovery."""
    if isinstance(ws, dict):
        kind = str(ws.get("kind") or "local").lower()
        wid = ws.get("id")
        root = ws.get("root_path")
        if kind == "ssh" and wid:
            mirrored = mirror_root(str(wid))
            return str(mirrored) if mirrored.exists() else None
        return str(root) if root else None
    if workspace_is_ssh(ws):
        mirrored = mirror_root(str(ws.id))
        return str(mirrored) if mirrored.exists() else None
    return ws.root_path


async def ensure_local_assets_root(ws: Workspace, *, force: bool = False) -> str:
    """Return local root for plugins/skills; SSH mirrors are TTL-cached.

    Concurrent callers for the same workspace share one sync (open + skills).
    """
    if not workspace_is_ssh(ws):
        return ws.root_path

    wid = str(ws.id)
    root = mirror_root(wid)
    ttl = _ttl_sec()
    now = time.monotonic()
    if (
        not force
        and ttl > 0
        and root.exists()
        and (now - _synced_at.get(wid, 0.0)) < ttl
    ):
        return str(root)

    async with _lock_for(wid):
        now = time.monotonic()
        if (
            not force
            and ttl > 0
            and root.exists()
            and (now - _synced_at.get(wid, 0.0)) < ttl
        ):
            return str(root)
        path = await sync_ssh_workspace_assets(ws)
        _synced_at[wid] = time.monotonic()
        return str(path)
