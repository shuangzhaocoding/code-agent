from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException

from code_agent.config import settings
from code_agent.policy.engine import is_protected

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


def try_read_text(path: Path, max_bytes: int = 1_048_576) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def split_patterns(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        parts = re.split(r"[,;\n]+", raw)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = part.strip().replace("\\", "/").lstrip("./")
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _is_glob(pat: str) -> bool:
    return any(ch in pat for ch in "*?[{")


def _match_scope(rel: str, pat: str) -> bool:
    rel = rel.replace("\\", "/")
    pat = pat.strip().replace("\\", "/").lstrip("./")
    if not pat:
        return True
    if _is_glob(pat):
        name = rel.split("/")[-1]
        return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
    return rel == pat or rel.startswith(pat + "/")


def path_in_scope(rel: str, includes: list[str], excludes: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    for exc in excludes:
        if _match_scope(rel, exc):
            return False
    if not includes:
        return True
    return any(_match_scope(rel, inc) for inc in includes)


def search_file_contents(
    root: str,
    query: str,
    extra_ignores: list[str] | None = None,
    limit: int = 80,
    per_file: int = 8,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    case_sensitive: bool = False,
) -> list[dict]:
    """Literal content search. Returns path/line/text hits."""
    q = (query or "").strip()
    if not q:
        return []
    extra = extra_ignores or []
    inc = includes or []
    exc = excludes or []
    if shutil.which("rg"):
        return _search_with_rg(root, q, extra, limit, per_file, inc, exc, case_sensitive)
    return _search_walk(root, q, extra, limit, per_file, inc, exc, case_sensitive)


def _rg_base_cmd(
    extra: list[str],
    includes: list[str],
    excludes: list[str],
    case_sensitive: bool,
    per_file: int | None,
) -> list[str]:
    cmd = ["rg", "--hidden", "--no-heading", "-F", "--max-filesize", "1M"]
    if not case_sensitive:
        cmd.append("-i")
    if per_file is not None:
        cmd.extend(["-m", str(per_file)])
    cmd.extend(["-g", "!node_modules", "-g", "!.git", "-g", "!*.min.js", "-g", "!*.min.css"])
    for pat in extra:
        if pat:
            cmd.extend(["-g", f"!{pat}"])
    for pat in excludes:
        cmd.extend(["-g", f"!{pat}", "-g", f"!{pat}/**"])
    for pat in includes:
        if _is_glob(pat):
            cmd.extend(["-g", pat])
    return cmd


def _rg_search_paths(base: Path, includes: list[str]) -> list[str]:
    paths = [str(base / inc) for inc in includes if not _is_glob(inc)]
    valid: list[str] = []
    for raw in paths:
        try:
            resolved = Path(raw).resolve()
            resolved.relative_to(base)
        except (OSError, ValueError):
            continue
        if resolved.exists():
            valid.append(str(resolved))
    return valid or [str(base)]


def _search_with_rg(
    root: str,
    query: str,
    extra: list[str],
    limit: int,
    per_file: int,
    includes: list[str],
    excludes: list[str],
    case_sensitive: bool,
) -> list[dict]:
    base = workspace_root(root)
    cmd = _rg_base_cmd(extra, includes, excludes, case_sensitive, per_file)
    cmd.append("-n")
    cmd.extend(["--", query, *_rg_search_paths(base, includes)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return []
    if proc.returncode not in (0, 1):
        return _search_walk(root, query, extra, limit, per_file, includes, excludes, case_sensitive)
    hits: list[dict] = []
    for raw in proc.stdout.splitlines():
        parsed = _parse_rg_line(raw, base)
        if not parsed:
            continue
        if not path_in_scope(parsed["path"], includes, excludes):
            continue
        hits.append(parsed)
        if len(hits) >= limit:
            break
    return hits


def _parse_rg_line(raw: str, base: Path) -> dict | None:
    # path:line:text  — Windows drive letters have extra colons
    parts = raw.split(":", 2)
    if len(parts) < 3:
        return None
    path_s, line_s, text = parts
    if not line_s.isdigit():
        rest = raw.split(":", 3)
        if len(rest) < 4 or not rest[2].isdigit():
            return None
        path_s = f"{rest[0]}:{rest[1]}"
        line_s = rest[2]
        text = rest[3]
    try:
        full = Path(path_s)
        rel = str(full.resolve().relative_to(base)).replace("\\", "/")
    except Exception:
        rel = path_s.replace("\\", "/")
        prefix = str(base).replace("\\", "/").rstrip("/") + "/"
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
    return {"path": rel, "line": int(line_s), "text": text.strip()[:240]}


def _line_matches(line: str, query: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return query in line
    return query.lower() in line.lower()


def _search_walk(
    root: str,
    query: str,
    extra: list[str],
    limit: int,
    per_file: int,
    includes: list[str],
    excludes: list[str],
    case_sensitive: bool,
) -> list[dict]:
    hits: list[dict] = []
    for rel, path in walk_files(root, extra):
        if not path_in_scope(rel, includes, excludes):
            continue
        text = try_read_text(path)
        if text is None:
            continue
        found = 0
        for i, line in enumerate(text.splitlines(), 1):
            if not _line_matches(line, query, case_sensitive):
                continue
            hits.append({"path": rel, "line": i, "text": line.strip()[:240]})
            found += 1
            if found >= per_file or len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    return hits


def _replace_count(text: str, query: str, replacement: str, case_sensitive: bool) -> tuple[str, int]:
    if case_sensitive:
        return text.replace(query, replacement), text.count(query)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    count = len(pattern.findall(text))
    if not count:
        return text, 0
    return pattern.sub(replacement, text), count


def _files_with_matches_rg(
    root: str,
    query: str,
    extra: list[str],
    includes: list[str],
    excludes: list[str],
    case_sensitive: bool,
    max_files: int,
) -> list[str] | None:
    base = workspace_root(root)
    cmd = _rg_base_cmd(extra, includes, excludes, case_sensitive, None)
    cmd.extend(["-l", "--", query, *_rg_search_paths(base, includes)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode not in (0, 1):
        return None
    out: list[str] = []
    for raw in proc.stdout.splitlines():
        try:
            full = Path(raw.strip()).resolve()
            rel = str(full.relative_to(base)).replace("\\", "/")
        except Exception:
            rel = raw.strip().replace("\\", "/")
            prefix = str(base).replace("\\", "/").rstrip("/") + "/"
            if rel.startswith(prefix):
                rel = rel[len(prefix) :]
        if not path_in_scope(rel, includes, excludes):
            continue
        out.append(rel)
        if len(out) >= max_files:
            break
    return out


def replace_file_contents(
    root: str,
    query: str,
    replacement: str,
    extra_ignores: list[str] | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    case_sensitive: bool = False,
    max_files: int = 200,
) -> dict:
    """Literal replace across matching files. Writes UTF-8 text files in place."""
    q = query or ""
    if not q:
        return {"files": 0, "replacements": 0, "skipped": [], "items": []}
    extra = extra_ignores or []
    inc = includes or []
    exc = excludes or []
    rels: list[str] | None = None
    if shutil.which("rg"):
        rels = _files_with_matches_rg(root, q, extra, inc, exc, case_sensitive, max_files)
    if rels is None:
        rels = []
        for rel, path in walk_files(root, extra, limit=8000):
            if not path_in_scope(rel, inc, exc):
                continue
            text = try_read_text(path)
            if text is None:
                continue
            _, count = _replace_count(text, q, replacement, case_sensitive)
            if not count:
                continue
            rels.append(rel)
            if len(rels) >= max_files:
                break

    items: list[dict] = []
    skipped: list[dict] = []
    total = 0
    for rel in rels:
        if is_protected(rel):
            skipped.append({"path": rel, "reason": "protected"})
            continue
        path = resolve_in_workspace(root, rel)
        if not path.is_file():
            skipped.append({"path": rel, "reason": "missing"})
            continue
        text = try_read_text(path)
        if text is None:
            skipped.append({"path": rel, "reason": "unreadable"})
            continue
        next_text, count = _replace_count(text, q, replacement, case_sensitive)
        if not count or next_text == text:
            continue
        try:
            path.write_text(next_text, encoding="utf-8")
        except OSError as err:
            skipped.append({"path": rel, "reason": str(err)})
            continue
        items.append({"path": rel, "count": count})
        total += count
    return {"files": len(items), "replacements": total, "skipped": skipped, "items": items}
