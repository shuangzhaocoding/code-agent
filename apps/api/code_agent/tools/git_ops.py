from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class GitError(RuntimeError):
    pass


def run_git(
    root: str | Path,
    args: list[str],
    timeout: int = 60,
    include_stderr: bool = True,
    ok_codes: tuple[int, ...] = (0,),
) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = proc.stdout or ""
    stderr = (proc.stderr or "").strip()
    if proc.returncode not in ok_codes:
        raise GitError((stdout + ("\n" + stderr if stderr else "")).strip() or f"git {' '.join(args)} failed ({proc.returncode})")
    if include_stderr and stderr:
        return (stdout + "\n" + stderr).strip()
    return stdout.strip()


def is_repo(root: str | Path) -> bool:
    try:
        run_git(root, ["rev-parse", "--is-inside-work-tree"])
        return True
    except (GitError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _norm_rel(path: str) -> str:
    return (path or "").replace("\\", "/").strip().lstrip("/")


def _under(path: str, prefix: str) -> bool:
    target = prefix.rstrip("/")
    return path == target or path.startswith(target + "/")


def parse_status(root: str | Path) -> dict[str, Any]:
    if not is_repo(root):
        return {"ok": False, "error": "not a git repository", "branch": "", "ahead": 0, "behind": 0, "files": []}
    raw = run_git(root, ["status", "-sb", "-z", "-uall", "--porcelain=v1"], include_stderr=False)
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
            target = Path(root) / path
            if target.is_dir():
                extra = run_git(
                    root,
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


def show_blob(root: str | Path, rel: str, rev: str = "HEAD") -> dict[str, Any]:
    if not _REV_BLOB_RE.fullmatch(rev or ""):
        raise GitError("invalid revision")
    path = _norm_rel(rel)
    if not path:
        raise GitError("path required")
    content = run_git(root, ["show", f"{rev}:{path}"], include_stderr=False)
    return {"path": path, "rev": rev, "content": content}


def discard_paths(root: str | Path, paths: list[str]) -> dict[str, Any]:
    wanted = [_norm_rel(p).rstrip("/") for p in paths if _norm_rel(p).rstrip("/")]
    wanted = [p for p in wanted if p not in {".", ".."} and not p.startswith("../")]
    if not wanted:
        return parse_status(root)
    status = parse_status(root)
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
        full = Path(root) / target
        if full.exists():
            untracked.append(target)
    if tracked:
        try:
            run_git(root, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *tracked])
        except GitError:
            run_git(root, ["checkout", "--", *tracked])
            try:
                run_git(root, ["reset", "-q", "HEAD", "--", *tracked])
            except GitError:
                pass
    if untracked:
        try:
            run_git(root, ["clean", "-fd", "--", *untracked])
        except GitError:
            for path in untracked:
                full = Path(root) / path
                if full.is_dir():
                    shutil.rmtree(full, ignore_errors=True)
                elif full.is_file() or full.is_symlink():
                    full.unlink(missing_ok=True)
    return parse_status(root)


def ignore_paths(root: str | Path, paths: list[str]) -> dict[str, Any]:
    patterns: list[str] = []
    for raw in paths:
        rel = _norm_rel(raw)
        if not rel or rel in {".", ".."} or rel.startswith("../"):
            continue
        pattern = rel
        full = Path(root) / rel.rstrip("/")
        if full.is_dir() and not pattern.endswith("/"):
            pattern = f"{pattern}/"
        if pattern not in patterns:
            patterns.append(pattern)
    if not patterns:
        return parse_status(root)
    gitignore = Path(root) / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    have = {line.strip() for line in existing.splitlines() if line.strip() and not line.strip().startswith("#")}
    added = [p for p in patterns if p not in have]
    if added:
        text = existing
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(added) + "\n"
        gitignore.write_text(text, encoding="utf-8")
    return parse_status(root)


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


def parse_log(root: str | Path, limit: int = 80) -> dict[str, Any]:
    if not is_repo(root):
        return {"ok": False, "error": "not a git repository", "head": "", "commits": []}
    n = max(1, min(int(limit or 80), 200))
    try:
        head = run_git(root, ["rev-parse", "HEAD"])
    except GitError:
        return {"ok": True, "head": "", "commits": []}
    try:
        out = run_git(root, ["log", "--all", "--topo-order", f"-{n}", f"--format={_LOG_FMT}"])
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


def parse_commit(root: str | Path, rev: str) -> dict[str, Any]:
    if not is_repo(root):
        return {"ok": False, "error": "not a git repository", "commit": None, "files": []}
    if not _REV_RE.fullmatch(rev or ""):
        return {"ok": False, "error": "invalid revision", "commit": None, "files": []}
    try:
        full = run_git(root, ["rev-parse", "--verify", f"{rev}^{{commit}}"], include_stderr=False)
        head = run_git(root, ["rev-parse", "HEAD"], include_stderr=False)
        meta_line = run_git(root, ["log", "-1", f"--format={_LOG_FMT}", full], include_stderr=False)
        commit = _parse_commit_meta(meta_line.splitlines()[0] if meta_line else "", head)
        if not commit:
            return {"ok": False, "error": "commit not found", "commit": None, "files": []}
        parents = commit["parents"]
        if parents:
            patch = run_git(
                root,
                ["diff", "--find-renames", "--no-color", parents[0], full],
                include_stderr=False,
                ok_codes=(0, 1),
            )
        else:
            patch = run_git(
                root,
                ["show", "--pretty=format:", "--find-renames", "--no-color", full],
                include_stderr=False,
                ok_codes=(0, 1),
            )
        return {"ok": True, "commit": commit, "files": split_git_diff(patch)}
    except (GitError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "commit": None, "files": []}


def file_diff(root: str | Path, rel: str, staged: bool = False) -> str:
    path = (rel or "").replace("\\", "/").lstrip("/")
    if not path:
        args = ["diff", "--no-color"]
        if staged:
            args.append("--cached")
        return run_git(root, args, include_stderr=False, ok_codes=(0, 1))
    if staged:
        return run_git(root, ["diff", "--cached", "--no-color", "--", path], include_stderr=False, ok_codes=(0, 1))
    out = run_git(root, ["diff", "--no-color", "--", path], include_stderr=False, ok_codes=(0, 1))
    if out:
        return out
    full = Path(root) / path
    if not full.is_file():
        return out
    return run_git(
        root,
        ["diff", "--no-index", "--no-color", "--", "/dev/null", path],
        include_stderr=False,
        ok_codes=(0, 1),
    )
