from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from code_agent.config import settings
from code_agent.plugins.base import registry
from code_agent.tools.context import get_run_id, get_workspace
from code_agent.tools.paths import read_text_file, resolve_in_workspace, walk_files
from code_agent.policy.engine import command_needs_confirm, is_command_blocked, is_protected
from code_agent.tools.approval import request_approval


async def _emit(block_type: str, meta: dict, text: str = "", complete: bool = True) -> None:
    from code_agent.protocol.events import new_id
    from code_agent.streaming.broker import broker

    run_id = get_run_id()
    block_id = new_id()
    await broker.publish(
        run_id,
        "block.started",
        {"block_id": block_id, "block_type": block_type, "meta": meta},
    )
    if text:
        await broker.publish(run_id, "block.delta", {"block_id": block_id, "text": text})
    if complete:
        await broker.publish(run_id, "block.completed", {"block_id": block_id, "status": "ok"})


def _root() -> str:
    return get_workspace()["root_path"]


@tool
async def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """Read a UTF-8 text file. Path may be workspace-relative or absolute (incl. ~)."""
    file_path = resolve_in_workspace(_root(), path)
    if not file_path.is_file():
        return f"ERROR: file not found: {path}"
    text = read_text_file(file_path)
    lines = text.splitlines()
    start = max(offset - 1, 0)
    end = min(start + max(limit, 1), len(lines))
    numbered = [f"{i + 1}|{lines[i]}" for i in range(start, end)]
    await _emit("file.read", {"path": path, "offset": offset, "limit": limit}, "\n".join(numbered[:40]))
    return f"{path} lines {start + 1}-{end} of {len(lines)}\n" + "\n".join(numbered)


@tool
async def list_dir(path: str = ".") -> str:
    """List a directory. Path may be workspace-relative or absolute (incl. ~)."""
    from code_agent.tools.paths import list_dir as _list

    items = _list(_root(), path)
    lines = [("📁 " if i["is_dir"] else "📄 ") + i["path"] for i in items]
    return "\n".join(lines) or "(empty)"


@tool
async def glob_search(pattern: str) -> str:
    """Find files by glob pattern relative to the workspace (e.g. **/*.py)."""
    import fnmatch

    matches = []
    for rel, _path in walk_files(_root()):
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern):
            matches.append(rel)
        if len(matches) >= 200:
            break
    return "\n".join(matches) or "(no matches)"


@tool
async def grep_search(query: str, glob: str = "", regex: bool = False) -> str:
    """Search file contents. Prefer literal query unless regex=True."""
    max_hits = int(settings.get("workspace.grep_max_hits") or 200)
    if shutil.which("rg"):
        cmd = ["rg", "-n", "--hidden", "--no-heading", "-m", "50", "-g", "!node_modules", "-g", "!.git"]
        if glob:
            cmd.extend(["-g", glob])
        if not regex:
            cmd.append("-F")
        cmd.extend([query, _root()])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "ERROR: grep timed out"
        lines = proc.stdout.splitlines()[:max_hits]
        return "\n".join(lines) or "(no matches)"

    flags = re.IGNORECASE
    cre = re.compile(query if regex else re.escape(query), flags)
    hits: list[str] = []
    for rel, path in walk_files(_root()):
        if glob:
            import fnmatch

            if not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(path.name, glob):
                continue
        try:
            text = read_text_file(path)
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if cre.search(line):
                hits.append(f"{rel}:{i}:{line[:240]}")
                if len(hits) >= max_hits:
                    return "\n".join(hits)
    return "\n".join(hits) or "(no matches)"


@tool
async def write_file(path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file. Path may be workspace-relative or absolute (incl. ~)."""
    if is_protected(path):
        return f"ERROR: protected file, cannot write: {path}"
    file_path = resolve_in_workspace(_root(), path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    old = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    file_path.write_text(content, encoding="utf-8")
    import difflib

    created = not old
    action = "create" if created else "overwrite"
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(True),
            content.splitlines(True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    await _emit(
        "file.diff",
        {
            "path": path,
            "action": action,
            "added": content.count("\n"),
            "removed": old.count("\n"),
            "before": old,
            "after": content,
        },
        diff,
    )
    return f"Wrote {path} ({len(content)} bytes)"


@tool
async def search_replace(path: str, old_string: str, new_string: str) -> str:
    """Replace the first exact occurrence of old_string with new_string. Path may be relative or absolute."""
    if is_protected(path):
        return f"ERROR: protected file: {path}"
    file_path = resolve_in_workspace(_root(), path)
    if not file_path.is_file():
        return f"ERROR: file not found: {path}"
    text = file_path.read_text(encoding="utf-8")
    if old_string not in text:
        return "ERROR: old_string not found"
    updated = text.replace(old_string, new_string, 1)
    file_path.write_text(updated, encoding="utf-8")
    import difflib

    diff = "".join(
        difflib.unified_diff(
            text.splitlines(True),
            updated.splitlines(True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    await _emit(
        "file.diff",
        {"path": path, "action": "edit", "before": text, "after": updated},
        diff,
    )
    return f"Updated {path}"


@tool
async def delete_file(path: str) -> str:
    """Delete a file or directory. Path may be workspace-relative or absolute (incl. ~)."""
    if is_protected(path):
        return f"ERROR: protected path, cannot delete: {path}"
    file_path = resolve_in_workspace(_root(), path)
    if not file_path.exists():
        return f"ERROR: not found: {path}"
    if not await request_approval("delete_file", f"删除 {path}", {"path": path}, kind="delete"):
        return "ERROR: user denied this operation"
    before = ""
    if file_path.is_file():
        try:
            before = file_path.read_text(encoding="utf-8")
        except Exception:
            before = ""
    if file_path.is_dir():
        shutil.rmtree(file_path)
    else:
        file_path.unlink()
    await _emit("file.delete", {"path": path, "action": "delete", "before": before, "after": ""})
    return f"Deleted {path}"


@tool
async def run_command(command: str, cwd: str = ".") -> str:
    """Run a shell command. cwd may be workspace-relative or absolute (incl. ~)."""
    if is_command_blocked(command):
        return f"ERROR: command blocked by policy: {command}"
    if command_needs_confirm(command):
        ok = await request_approval(
            "run_command",
            f"运行命令：{command}",
            {"command": command, "cwd": cwd},
            kind="command",
        )
        if not ok:
            return "ERROR: user denied this operation"
    work = resolve_in_workspace(_root(), cwd)
    if not work.is_dir():
        work = resolve_in_workspace(_root(), ".")
    timeout = int(settings.get("agent.tool_timeout_sec") or 90)
    max_chars = int(settings.get("agent.max_tool_output_chars") or 12000)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timed out after {timeout}s"
    output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if len(output) > max_chars:
        output = output[:max_chars] + "\n...[truncated]"
    await _emit(
        "terminal",
        {"command": command, "cwd": cwd, "exit_code": proc.returncode},
        output[-4000:],
    )
    return f"exit {proc.returncode}\n{output}"


@tool
async def list_skills() -> str:
    """List available agent skills (name + description). Load one with load_skill before following it."""
    from code_agent.skills.registry import list_skill_catalog

    items = list_skill_catalog(get_workspace()["root_path"])
    enabled = [s for s in items if s.get("enabled") and not s.get("invalid_reason")]
    if not enabled:
        return "(no skills)"
    return "\n".join(f"- {s['name']}: {s['description']}" for s in enabled)


@tool
async def load_skill(name: str) -> str:
    """Load the full SKILL.md body for a skill. Call when the task matches a listed skill."""
    from code_agent.skills.registry import load_skill_body

    body = load_skill_body(get_workspace()["root_path"], name)
    if not body:
        return f"ERROR: skill not found: {name}"
    await _emit("skill.activated", {"name": name}, body[:500])
    return body


def register_builtin_tools() -> None:
    for t, modes in [
        (read_file, ("ask", "agent", "plan")),
        (list_dir, ("ask", "agent", "plan")),
        (glob_search, ("ask", "agent", "plan")),
        (grep_search, ("ask", "agent", "plan")),
        (list_skills, ("ask", "agent", "plan")),
        (load_skill, ("ask", "agent", "plan")),
        (write_file, ("agent",)),
        (search_replace, ("agent",)),
        (delete_file, ("agent",)),
        (run_command, ("agent",)),
    ]:
        registry.register_tool(t, source="builtin", modes=modes)
