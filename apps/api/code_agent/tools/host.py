from __future__ import annotations

import asyncio

from langchain_core.tools import tool

from code_agent.config import settings
from code_agent.plugins.base import registry
from code_agent.tools.context import get_run_id, get_workspace
from code_agent.policy.engine import is_command_blocked, is_protected
from code_agent.tools.approval import request_approval


async def _run_sync(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


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


async def _backend():
    from code_agent.db.models import Workspace
    from code_agent.workspace.backend import get_workspace_backend
    from code_agent.workspace.local import LocalWorkspaceBackend

    ctx = get_workspace()
    wid = ctx.get("id")
    if wid:
        row = await Workspace.get_or_none(id=wid)
        if row:
            return await get_workspace_backend(row)
    # Fallback for legacy context with only root_path
    class _Tmp:
        root_path = ctx["root_path"]
        ignore_globs = []
        kind = "local"

    return LocalWorkspaceBackend(_Tmp())  # type: ignore[arg-type]


def _root() -> str:
    return get_workspace()["root_path"]


@tool
async def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """Read a UTF-8 text file. Path may be workspace-relative or absolute (incl. ~)."""
    fs = await _backend()
    if not await fs.is_file(path):
        return f"ERROR: file not found: {path}"
    try:
        text = await fs.read_text(path)
    except Exception as exc:
        return f"ERROR: {exc}"
    lines = text.splitlines()
    start = max(offset - 1, 0)
    end = min(start + max(limit, 1), len(lines))
    numbered = [f"{i + 1}|{lines[i]}" for i in range(start, end)]
    await _emit("file.read", {"path": path, "offset": offset, "limit": limit}, "\n".join(numbered[:40]))
    return f"{path} lines {start + 1}-{end} of {len(lines)}\n" + "\n".join(numbered)


@tool
async def list_dir(path: str = ".") -> str:
    """List a directory. Path may be workspace-relative or absolute (incl. ~)."""
    fs = await _backend()
    try:
        items = await fs.list_dir(path)
    except Exception as exc:
        return f"ERROR: {exc}"
    lines = [("📁 " if i["is_dir"] else "📄 ") + i["path"] for i in items]
    return "\n".join(lines) or "(empty)"


@tool
async def glob_search(pattern: str) -> str:
    """Find files by glob pattern relative to the workspace (e.g. **/*.py)."""
    import fnmatch

    fs = await _backend()
    matches = []
    for rel, _abs in await fs.walk_files():
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel.split("/")[-1], pattern):
            matches.append(rel)
        if len(matches) >= 200:
            break
    return "\n".join(matches) or "(no matches)"


@tool
async def grep_search(query: str, glob: str = "", regex: bool = False) -> str:
    """Search file contents. Prefer literal query unless regex=True."""
    max_hits = int(settings.get("workspace.grep_max_hits") or 200)
    fs = await _backend()
    include = [glob] if glob else None
    hits = await fs.search(query, regex=regex, include=include, max_hits=max_hits)
    if not hits:
        return "(no matches)"
    return "\n".join(f"{h['path']}:{h.get('line', 0)}:{h.get('text', '')}" for h in hits)


@tool
async def write_file(path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file. Path may be workspace-relative or absolute (incl. ~)."""
    if is_protected(path):
        return f"ERROR: protected file, cannot write: {path}"
    if not await request_approval("write_file", f"写入 {path}", {"path": path}, kind="write"):
        return "ERROR: user denied this operation"
    fs = await _backend()
    old = ""
    try:
        if await fs.is_file(path):
            old = await fs.read_text(path)
    except Exception:
        old = ""
    await fs.write_text(path, content)
    import difflib

    action = "create" if not old else "overwrite"
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
    if not await request_approval(
        "search_replace",
        f"编辑 {path}",
        {"path": path},
        kind="write",
    ):
        return "ERROR: user denied this operation"
    fs = await _backend()
    if not await fs.is_file(path):
        return f"ERROR: file not found: {path}"
    try:
        text = await fs.read_text(path)
    except Exception as exc:
        return f"ERROR: {exc}"
    if old_string not in text:
        return "ERROR: old_string not found"
    updated = text.replace(old_string, new_string, 1)
    await fs.write_text(path, updated)
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
    fs = await _backend()
    if not await fs.exists(path):
        return f"ERROR: not found: {path}"
    if not await request_approval("delete_file", f"删除 {path}", {"path": path}, kind="delete"):
        return "ERROR: user denied this operation"
    before = ""
    try:
        if await fs.is_file(path):
            before = await fs.read_text(path)
    except Exception:
        before = ""
    await fs.delete(path)
    await _emit("file.delete", {"path": path, "action": "delete", "before": before, "after": ""})
    return f"Deleted {path}"


@tool
async def apply_patch(patch: str, path: str = "") -> str:
    """Apply a structured patch to one or more files. Prefer this over write_file for existing files.

    Use this format (one or more files):

    *** Begin Patch
    *** Update File: relative/path.py
    @@
     context line
    -old line
    +new line
    *** Add File: relative/new.py
    +print("hello")
    *** Delete File: relative/obsolete.py
    *** End Patch

    Unified diffs (--- / +++ / @@) are also accepted. Keep context lines accurate.
    """
    from code_agent.tools.patch import PatchError, apply_file_patch, parse_patch

    try:
        ops = parse_patch(patch, default_path=path.strip())
    except PatchError as exc:
        return f"ERROR: {exc}"
    if not ops:
        return "ERROR: empty patch"
    fs = await _backend()
    paths = [op.path for op in ops]
    protected = [p for p in paths if is_protected(p)]
    if protected:
        return f"ERROR: protected file, cannot patch: {', '.join(protected)}"
    has_delete = any(op.kind == "delete" for op in ops)
    label = f"应用补丁：{', '.join(paths[:6])}" + ("…" if len(paths) > 6 else "")
    if not await request_approval(
        "apply_patch",
        label,
        {"path": paths[0], "paths": paths, "has_delete": has_delete},
        kind="delete" if has_delete else "write",
    ):
        return "ERROR: user denied this operation"

    plan: list[tuple[str, str, str, str]] = []
    for op in ops:
        old = ""
        existed = await fs.is_file(op.path)
        if existed:
            try:
                old = await fs.read_text(op.path)
            except Exception as exc:
                return f"ERROR: {op.path}: {exc}"
        elif op.kind == "update":
            return f"ERROR: file not found: {op.path}"
        elif op.kind == "add" and existed:
            return f"ERROR: file already exists: {op.path} (use Update File)"
        try:
            new = apply_file_patch(old if existed else None, op)
        except PatchError as exc:
            return f"ERROR: {op.path}: {exc}"
        action = "delete" if new is None else ("create" if not existed else "edit")
        plan.append((op.path, action, old, new if new is not None else ""))

    import difflib

    written: list[str] = []
    for rel, action, old, new in plan:
        if action == "delete":
            await fs.delete(rel)
            await _emit("file.delete", {"path": rel, "action": "delete", "before": old, "after": ""})
            written.append(f"deleted {rel}")
            continue
        await fs.write_text(rel, new)
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(True),
                new.splitlines(True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
        await _emit(
            "file.diff",
            {
                "path": rel,
                "action": action,
                "added": new.count("\n"),
                "removed": old.count("\n"),
                "before": old,
                "after": new,
            },
            diff,
        )
        written.append(f"{action} {rel}")
    return "Patched " + "; ".join(written)


@tool
async def todo_write(todos: list | str) -> str:
    """Replace the current task checklist. Call this for multi-step work and keep it updated.

    `todos` is an array of objects: [{"id":"1","content":"Inspect auth flow","status":"in_progress"}].
    status: pending | in_progress | completed | cancelled. At most one item may be in_progress.
    Always send the full list (not a delta).
    """
    from code_agent.tools.todos import normalize_todos, render_todo_text, todo_summary

    try:
        items = normalize_todos(todos)
    except ValueError as exc:
        return f"ERROR: {exc}"
    text = render_todo_text(items)
    summary = todo_summary(items)
    await _emit("todo", {"items": items, **summary}, text)
    return text


@tool
async def run_command(command: str, cwd: str = ".") -> str:
    """Run a shell command. cwd may be workspace-relative or absolute (incl. ~)."""
    if is_command_blocked(command):
        return f"ERROR: command blocked by policy: {command}"
    if not await request_approval(
        "run_command",
        f"运行命令：{command}",
        {"command": command, "cwd": cwd},
        kind="command",
    ):
        return "ERROR: user denied this operation"
    fs = await _backend()
    timeout = int(settings.get("agent.tool_timeout_sec") or 90)
    max_chars = int(settings.get("agent.max_tool_output_chars") or 12000)
    code, stdout, stderr = await fs.run_command(command, cwd=cwd, timeout=timeout)
    output = stdout + (("\n" + stderr) if stderr else "")
    if len(output) > max_chars:
        output = output[:max_chars] + "\n...[truncated]"
    await _emit(
        "terminal",
        {"command": command, "cwd": cwd, "exit_code": code},
        output[-4000:],
    )
    return f"exit {code}\n{output}"


@tool
async def list_skills() -> str:
    """List available agent skills (name + description). Load one with load_skill before following it."""
    from code_agent.db.models import Workspace
    from code_agent.skills.registry import ensure_skills_ready, list_skill_catalog

    ctx = get_workspace()
    ws = None
    wid = ctx.get("id")
    if wid:
        ws = await Workspace.get_or_none(id=wid)
        if ws:
            await ensure_skills_ready(ws)
    items = list_skill_catalog(ws or ctx.get("root_path"))
    enabled = [s for s in items if s.get("enabled") and not s.get("invalid_reason")]
    if not enabled:
        return "(no skills)"
    return "\n".join(f"- {s['name']}: {s['description']}" for s in enabled)


@tool
async def load_skill(name: str) -> str:
    """Load the full SKILL.md body for a skill. Call when the task matches a listed skill."""
    from code_agent.db.models import Workspace
    from code_agent.skills.registry import ensure_skills_ready, load_skill_body

    ctx = get_workspace()
    ws = None
    wid = ctx.get("id")
    if wid:
        ws = await Workspace.get_or_none(id=wid)
        if ws:
            await ensure_skills_ready(ws)
    body = load_skill_body(ws or ctx.get("root_path"), name)
    if not body:
        return f"ERROR: skill not found: {name}"
    await _emit("skill.activated", {"name": name}, body[:500])
    return body


def register_builtin_tools() -> None:
    from code_agent.mcp.bridge import register_mcp_plugin
    from code_agent.plugins.base import PluginInfo
    from code_agent.tools.explore import explore_codebase

    registry.loading_plugin_id = "builtin.tools"
    for t, modes in [
        (read_file, ("ask", "agent", "plan")),
        (list_dir, ("ask", "agent", "plan")),
        (glob_search, ("ask", "agent", "plan")),
        (grep_search, ("ask", "agent", "plan")),
        (explore_codebase, ("ask", "agent", "plan")),
        (list_skills, ("ask", "agent", "plan")),
        (load_skill, ("ask", "agent", "plan")),
        (todo_write, ("ask", "agent", "plan")),
        (write_file, ("agent",)),
        (search_replace, ("agent",)),
        (apply_patch, ("agent",)),
        (delete_file, ("agent",)),
        (run_command, ("agent",)),
    ]:
        registry.register_tool(t, source="builtin", modes=modes)
    registry.register_plugin(
        PluginInfo(
            plugin_id="builtin.tools",
            source="builtin",
            title="内置工作区工具",
            description="读写文件、搜索、终端命令等核心 Agent 工具。",
            kind="tools",
            origin="builtin",
            contributes=("tools",),
            author="Code Agent",
            icon="wrench",
            accent="#4f6bff",
            keywords=("files", "terminal", "search", "skills", "patch", "todo", "explore"),
        )
    )
    registry.loading_plugin_id = ""
    register_mcp_plugin()
