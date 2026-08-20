from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from fastapi import HTTPException

from code_agent.config import settings

DEFAULT_IGNORES = list(settings.get("workspace.default_ignores") or [])
TREE_IGNORES = list(
    settings.get("workspace.tree_ignores")
    or [".git", ".code-agent/data"]
)


class PathEscapeError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=403, detail={"code": "path.escape", "message": "Path is outside the workspace"})


def workspace_root(root: str) -> Path:
    return Path(root).expanduser().resolve()


def resolve_in_workspace(root: str, rel: str) -> Path:
    """Resolve a path for tools/APIs.

    - Relative paths resolve against the workspace root (also supports ``..``).
    - Absolute paths and ``~`` are allowed with no workspace sandbox.
    """
    base = workspace_root(root)
    raw = (rel or ".").strip() or "."
    if raw.startswith("~"):
        return Path(raw).expanduser().resolve()
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / raw).resolve()


def matches_ignore(rel: str, patterns: list[str]) -> bool:
    name = rel.replace("\\", "/")
    parts = name.split("/")
    for pat in patterns:
        if not pat:
            continue
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(parts[0] if parts else name, pat):
            return True
        if any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
    return False


def is_ignored(rel: str, extra: list[str] | None = None) -> bool:
    """Full ignore set for search / walk (defaults + gitignore + workspace globs)."""
    return matches_ignore(rel, DEFAULT_IGNORES + (extra or []))


def load_ignore_file(root: str) -> list[str]:
    extra: list[str] = []
    base = workspace_root(root)
    for name in (".gitignore", ".codeagentignore"):
        path = base / name
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    extra.append(line.rstrip("/"))
    return extra


def read_text_file(path: Path, max_bytes: int | None = None) -> str:
    limit = max_bytes or int(settings.get("workspace.max_file_bytes") or 1048576)
    size = path.stat().st_size
    if size > limit:
        raise HTTPException(
            status_code=400,
            detail={"code": "file.too_large", "message": f"File exceeds {limit} bytes"},
        )
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise HTTPException(status_code=400, detail={"code": "file.binary", "message": "Binary file"})
    return data.decode("utf-8", errors="replace")


def list_dir(root: str, rel: str = "", extra_ignores: list[str] | None = None) -> list[dict]:
    """List one directory for the explorer tree.

    Uses ``tree_ignores`` only (not ``default_ignores`` / ``.gitignore``), so
    dependency dirs like ``node_modules`` and ``venv`` remain browsable.
    Search/walk still use the full ignore set via ``is_ignored``.
    """
    path = resolve_in_workspace(root, rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "path.not_found", "message": "Not found"})
    if not path.is_dir():
        raise HTTPException(status_code=400, detail={"code": "path.not_dir", "message": "Not a directory"})
    ignores = TREE_IGNORES + (extra_ignores or [])
    max_children = int(settings.get("workspace.tree_max_children") or 400)
    items = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "path.denied", "message": str(exc)})
    for child in entries:
        try:
            rel_child = str(child.relative_to(workspace_root(root))).replace("\\", "/")
        except ValueError:
            rel_child = str(child)
        if matches_ignore(rel_child, ignores):
            continue
        items.append(
            {
                "name": child.name,
                "path": rel_child,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None,
            }
        )
        if len(items) >= max_children:
            break
    return items


def walk_files(root: str, extra_ignores: list[str] | None = None, limit: int = 5000):
    base = workspace_root(root)
    ignores = load_ignore_file(root) + (extra_ignores or [])
    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base)
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d
            for d in dirnames
            if not is_ignored(f"{rel_dir}/{d}".lstrip("/"), ignores)
        ]
        for name in filenames:
            rel = f"{rel_dir}/{name}".lstrip("/").replace("\\", "/")
            if is_ignored(rel, ignores):
                continue
            yield rel, Path(dirpath) / name
            count += 1
            if count >= limit:
                return
