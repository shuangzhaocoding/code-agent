from __future__ import annotations

import re
import shlex
from typing import Any

from code_agent.workspace.backend import WorkspaceBackend


class GitError(RuntimeError):
    pass


async def run_git(
    backend: WorkspaceBackend,
    args: list[str],
    timeout: int = 60,
    include_stderr: bool = True,
    ok_codes: tuple[int, ...] = (0,),
) -> str:
    cmd = "git " + " ".join(shlex.quote(a) for a in args)
    code, stdout, stderr = await backend.run_command(cmd, cwd=".", timeout=timeout)
    out = stdout or ""
    err = (stderr or "").strip()
    if code == 127 or (code != 0 and "not found" in err.lower() and "git" in err.lower()):
        raise FileNotFoundError("git is not installed")
    if code not in ok_codes:
        raise GitError((out + ("\n" + err if err else "")).strip() or f"git {' '.join(args)} failed ({code})")
    if include_stderr and err:
        return (out + "\n" + err).strip()
    return out.strip()


async def is_repo(backend: WorkspaceBackend) -> bool:
    try:
        await run_git(backend, ["rev-parse", "--is-inside-work-tree"])
        return True
    except (GitError, FileNotFoundError, TimeoutError):
        return False


def _norm_rel(path: str) -> str:
    return (path or "").replace("\\", "/").strip().lstrip("/")


def _under(path: str, prefix: str) -> bool:
    target = prefix.rstrip("/")
    return path == target or path.startswith(target + "/")


def safe_rel_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    for raw in paths:
        rel = _norm_rel(raw)
        if not rel or rel in {".", ".."} or rel.startswith("../") or "/../" in f"/{rel}/":
            continue
        out.append(rel)
    return out


async def parse_status(backend: WorkspaceBackend) -> dict[str, Any]:
    if not await is_repo(backend):
        return {"ok": False, "error": "not a git repository", "branch": "", "ahead": 0, "behind": 0, "files": []}
    raw = await run_git(backend, ["status", "-sb", "-z", "-uall", "--porcelain=v1"], include_stderr=False)
    chunks = raw.split("\0")
    branch = ""
    ahead = 0
    behind = 0
    files: list[dict[str, Any]] = []
    if chunks and chunks[0].startswith("##"):
        header = chunks[0][3:]
        m = re.match(r"([^\s.]+)(?:\.\.\.(\S+))?(?: \[(.+)\])?", header)
        if m:
            branch = m.group(1)
            extra = m.group(3) or ""
            am = re.search(r"ahead (\d+)", extra)
            bm = re.search(r"behind (\d+)", extra)
            ahead = int(am.group(1)) if am else 0
            behind = int(bm.group(1)) if bm else 0
        else:
            branch = header.split()[0]
        chunks = chunks[1:]
    i = 0
    while i < len(chunks):
        rec = chunks[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, path = rec[:2], rec[3:].replace("\\", "/")
        if xy[0] in {"R", "C"} and i < len(chunks) and chunks[i] and (len(chunks[i]) < 2 or chunks[i][1] != " "):
            path = chunks[i].replace("\\", "/")
            i += 1
        elif " -> " in path:
            path = path.split(" -> ", 1)[-1]
        path = path.rstrip("/")
        if not path:
            continue
        staged = xy[0] not in {" ", "?"}
        unstaged = xy[1] not in {" ", "?"}
        code = xy.strip() or xy[1]
        if xy == "??":
            code = "?"
            if await backend.is_dir(path):
                extra = await run_git(
                    backend,
                    ["ls-files", "-z", "--others", "--exclude-standard", "--", path or "."],
                    include_stderr=False,
                )
                added = False
                for rel in extra.split("\0"):
                    rel = _norm_rel(rel).rstrip("/")
                    if rel:
                        files.append({"path": rel, "code": "?", "staged": False, "unstaged": True})
                        added = True
                if added:
                    continue
        files.append({"path": path, "code": code, "staged": staged, "unstaged": unstaged or xy == "??"})
    uniq: dict[str, dict[str, Any]] = {}
    for item in files:
        uniq[item["path"]] = item
    return {"ok": True, "branch": branch, "ahead": ahead, "behind": behind, "files": list(uniq.values())}


_REV_BLOB_RE = re.compile(r"^(HEAD|[0-9a-fA-F]{7,40})$")


async def show_blob(backend: WorkspaceBackend, rel: str, rev: str = "HEAD") -> dict[str, Any]:
    if not _REV_BLOB_RE.fullmatch(rev or ""):
        raise GitError("invalid revision")
    path = _norm_rel(rel)
    if not path:
        raise GitError("path required")
    content = await run_git(backend, ["show", f"{rev}:{path}"], include_stderr=False)
    return {"path": path, "rev": rev, "content": content}


async def discard_paths(backend: WorkspaceBackend, paths: list[str]) -> dict[str, Any]:
    wanted = [_norm_rel(p).rstrip("/") for p in paths if _norm_rel(p).rstrip("/")]
    wanted = [p for p in wanted if p not in {".", ".."} and not p.startswith("../")]
    if not wanted:
        return await parse_status(backend)
    status = await parse_status(backend)
    tracked: list[str] = []
    untracked: list[str] = []
    seen: set[str] = set()
    for item in status.get("files") or []:
        path = str(item.get("path") or "")
        if not path or path in seen or not any(_under(path, w) for w in wanted):
            continue
        seen.add(path)
        if item.get("code") == "?":
            untracked.append(path)
        else:
            tracked.append(path)
    for target in wanted:
        if any(_under(path, target) for path in seen):
            continue
        if await backend.exists(target):
            untracked.append(target)
    if tracked:
        try:
            await run_git(backend, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *tracked])
        except GitError:
            await run_git(backend, ["checkout", "--", *tracked])
            try:
                await run_git(backend, ["reset", "-q", "HEAD", "--", *tracked])
            except GitError:
                pass
    if untracked:
        try:
            await run_git(backend, ["clean", "-fd", "--", *untracked])
        except GitError:
            for path in untracked:
                try:
                    if await backend.exists(path):
                        await backend.delete(path)
                except Exception:
                    pass
    return await parse_status(backend)


async def ignore_paths(backend: WorkspaceBackend, paths: list[str]) -> dict[str, Any]:
    patterns: list[str] = []
    for raw in paths:
        rel = _norm_rel(raw)
        if not rel or rel in {".", ".."} or rel.startswith("../"):
            continue
        pattern = rel
        if await backend.is_dir(rel.rstrip("/")) and not pattern.endswith("/"):
            pattern = f"{pattern}/"
        if pattern not in patterns:
            patterns.append(pattern)
    if not patterns:
        return await parse_status(backend)
    existing = ""
    try:
        if await backend.is_file(".gitignore"):
            existing = await backend.read_text(".gitignore")
    except Exception:
        existing = ""
    have = {line.strip() for line in existing.splitlines() if line.strip() and not line.strip().startswith("#")}
    added = [p for p in patterns if p not in have]
    if added:
        text = existing
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(added) + "\n"
        await backend.write_text(".gitignore", text)
    return await parse_status(backend)


_LOG_SEP = "\x1f"
_LOG_FMT = f"%H{_LOG_SEP}%h{_LOG_SEP}%P{_LOG_SEP}%an{_LOG_SEP}%ae{_LOG_SEP}%aI{_LOG_SEP}%D{_LOG_SEP}%s"


def _parse_refs(raw: str) -> list[str]:
    refs: list[str] = []
    for part in (p.strip() for p in (raw or "").split(",") if p.strip()):
        if part.startswith("HEAD -> "):
            refs.append("HEAD")
            refs.append(part[8:].strip())
        elif part == "HEAD":
            refs.append("HEAD")
        else:
            refs.append(part)
    return refs


async def parse_log(backend: WorkspaceBackend, limit: int = 80) -> dict[str, Any]:
    if not await is_repo(backend):
        return {"ok": False, "error": "not a git repository", "head": "", "commits": []}
    n = max(1, min(int(limit or 80), 200))
    try:
        head = await run_git(backend, ["rev-parse", "HEAD"])
    except GitError:
        return {"ok": True, "head": "", "commits": []}
    try:
        out = await run_git(backend, ["log", "--all", "--topo-order", f"-{n}", f"--format={_LOG_FMT}"])
    except GitError as exc:
        return {"ok": False, "error": str(exc), "head": head, "commits": []}
    commits: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(_LOG_SEP)
        if len(parts) < 8:
            parts = parts + [""] * (8 - len(parts))
        full, short, parents, author, email, date, deco, subject = parts[:8]
        commits.append(
            {
                "hash": full,
                "short": short,
                "parents": [p for p in parents.split() if p],
                "author": author,
                "email": email,
                "date": date,
                "refs": _parse_refs(deco),
                "subject": subject,
                "is_head": full == head,
            }
        )
    return {"ok": True, "head": head, "commits": commits}


_REV_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_MAX_PATCH_CHARS = 160_000


def _unquote_git_path(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    return text


def _parse_commit_meta(line: str, head: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    parts = line.split(_LOG_SEP)
    if len(parts) < 8:
        parts = parts + [""] * (8 - len(parts))
    full, short, parents, author, email, date, deco, subject = parts[:8]
    return {
        "hash": full,
        "short": short,
        "parents": [p for p in parents.split() if p],
        "author": author,
        "email": email,
        "date": date,
        "refs": _parse_refs(deco),
        "subject": subject,
        "is_head": full == head,
    }


def split_git_diff(text: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    lines: list[str] = []

    def flush() -> None:
        if not current:
            return
        patch = "\n".join(lines)
        if len(patch) > _MAX_PATCH_CHARS:
            current["truncated"] = True
            patch = patch[:_MAX_PATCH_CHARS] + "\n… diff 过长，已截断"
        current["patch"] = patch
        files.append(current)

    for line in (text or "").splitlines():
        match = _DIFF_GIT_RE.match(line)
        if match:
            flush()
            old_path = _unquote_git_path(match.group(1))
            new_path = _unquote_git_path(match.group(2))
            current = {
                "path": new_path or old_path,
                "old_path": old_path if old_path != new_path else "",
                "status": "M",
                "additions": 0,
                "deletions": 0,
                "binary": False,
                "truncated": False,
            }
            lines = [line]
            continue
        if current is None:
            continue
        lines.append(line)
        if line.startswith("new file mode"):
            current["status"] = "A"
        elif line.startswith("deleted file mode"):
            current["status"] = "D"
        elif line.startswith("rename from "):
            current["status"] = "R"
            current["old_path"] = _unquote_git_path(line[12:])
        elif line.startswith("rename to "):
            current["path"] = _unquote_git_path(line[10:])
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            current["binary"] = True
        elif line.startswith("+") and not line.startswith("+++"):
            current["additions"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            current["deletions"] += 1
    flush()
    return files


async def parse_commit(backend: WorkspaceBackend, rev: str) -> dict[str, Any]:
    if not await is_repo(backend):
        return {"ok": False, "error": "not a git repository", "commit": None, "files": []}
    if not _REV_RE.fullmatch(rev or ""):
        return {"ok": False, "error": "invalid revision", "commit": None, "files": []}
    try:
        full = await run_git(backend, ["rev-parse", "--verify", f"{rev}^{{commit}}"], include_stderr=False)
        head = await run_git(backend, ["rev-parse", "HEAD"], include_stderr=False)
        meta_line = await run_git(backend, ["log", "-1", f"--format={_LOG_FMT}", full], include_stderr=False)
        commit = _parse_commit_meta(meta_line.splitlines()[0] if meta_line else "", head)
        if not commit:
            return {"ok": False, "error": "commit not found", "commit": None, "files": []}
        parents = commit["parents"]
        if parents:
            patch = await run_git(
                backend,
                ["diff", "--find-renames", "--no-color", parents[0], full],
                include_stderr=False,
                ok_codes=(0, 1),
            )
        else:
            patch = await run_git(
                backend,
                ["show", "--pretty=format:", "--find-renames", "--no-color", full],
                include_stderr=False,
                ok_codes=(0, 1),
            )
        return {"ok": True, "commit": commit, "files": split_git_diff(patch)}
    except (GitError, FileNotFoundError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc), "commit": None, "files": []}


async def file_diff(backend: WorkspaceBackend, rel: str, staged: bool = False) -> str:
    path = (rel or "").replace("\\", "/").lstrip("/")
    if not path:
        args = ["diff", "--no-color"]
        if staged:
            args.append("--cached")
        return await run_git(backend, args, include_stderr=False, ok_codes=(0, 1))
    if staged:
        return await run_git(
            backend, ["diff", "--cached", "--no-color", "--", path], include_stderr=False, ok_codes=(0, 1)
        )
    out = await run_git(backend, ["diff", "--no-color", "--", path], include_stderr=False, ok_codes=(0, 1))
    if out:
        return out
    if not await backend.is_file(path):
        return out
    return await run_git(
        backend,
        ["diff", "--no-index", "--no-color", "--", "/dev/null", path],
        include_stderr=False,
        ok_codes=(0, 1),
    )
