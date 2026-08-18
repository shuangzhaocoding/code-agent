from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


class GitError(RuntimeError):
    pass


def run_git(root: str | Path, args: list[str], timeout: int = 60) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if proc.returncode != 0:
        raise GitError(out.strip() or f"git {' '.join(args)} failed ({proc.returncode})")
    return out.strip()


def is_repo(root: str | Path) -> bool:
    try:
        run_git(root, ["rev-parse", "--is-inside-work-tree"])
        return True
    except (GitError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def parse_status(root: str | Path) -> dict[str, Any]:
    if not is_repo(root):
        return {"ok": False, "error": "not a git repository", "branch": "", "ahead": 0, "behind": 0, "files": []}
    branch_out = run_git(root, ["status", "-sb", "--porcelain=v1"])
    lines = branch_out.splitlines()
    branch = ""
    ahead = 0
    behind = 0
    files: list[dict[str, Any]] = []
    if lines and lines[0].startswith("##"):
        header = lines[0][3:]
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
        lines = lines[1:]
    for line in lines:
        if len(line) < 4:
            continue
        xy, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        staged = xy[0] not in {" ", "?"}
        unstaged = xy[1] not in {" ", "?"}
        code = xy.strip() or xy[1]
        if xy == "??":
            code = "?"
        files.append({"path": path, "code": code, "staged": staged, "unstaged": unstaged or xy == "??"})
    return {"ok": True, "branch": branch, "ahead": ahead, "behind": behind, "files": files}
