from __future__ import annotations

import re
from typing import Any

from code_agent.editor.inline_edit import strip_code_fences
from code_agent.tools.git_ops import file_diff, parse_status, safe_rel_paths
from code_agent.workspace.backend import WorkspaceBackend

COMMIT_TYPES = (
    "feat",
    "fix",
    "refactor",
    "perf",
    "docs",
    "test",
    "chore",
    "style",
    "build",
    "ci",
    "revert",
)

COMMIT_SYSTEM = f"""You write git commit messages in Conventional Commits format.
Return ONLY the commit message — no markdown fences, no quotes, no commentary.

Format:
<type>(<optional-scope>): <subject>

<body — optional: why and what changed, not a file dump>

Rules:
- type MUST be one of: {", ".join(COMMIT_TYPES)}
- type and scope stay English lowercase; never translate them (e.g. feat, not 功能)
- pick the single primary type that best matches the change
- scope is a short module/area noun; omit it when unclear
- subject: imperative, whole first line ≤72 characters, no trailing period
- do not mention that you are an AI
"""

_TYPE_RE = re.compile(
    rf"^({'|'.join(COMMIT_TYPES)})(\([^)]+\))?\s*:\s*(.+)$",
    re.IGNORECASE,
)

_LOCALE_LANG = {
    "zh": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
}

_MAX_FILES = 12
_PER_FILE = 3500
_TOTAL = 20000


def clean_commit_message(raw: str) -> str:
    text = strip_code_fences(raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'", "`"}:
        text = text[1:-1].strip()
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines[0] = _normalize_type_prefix(lines[0].strip().rstrip("。．."))
    return "\n".join(lines).strip()


def _normalize_type_prefix(subject: str) -> str:
    match = _TYPE_RE.match(subject)
    if not match:
        return subject
    kind = match.group(1).lower()
    scope_raw = match.group(2) or ""
    inner = scope_raw[1:-1].strip().lower() if scope_raw else ""
    scope = f"({inner})" if inner else ""
    rest = match.group(3).strip()
    return f"{kind}{scope}: {rest}"


def build_commit_ai_prompt(
    *,
    branch: str,
    paths: list[str],
    diff: str,
    locale: str = "zh",
    hint: str = "",
) -> str:
    lang = _LOCALE_LANG.get((locale or "zh").strip().lower(), "English")
    parts = [
        f"Write the subject and optional body in {lang}. Keep type and scope in English.",
        "First line must be `<type>(<scope>): <subject>` or `<type>: <subject>`.",
    ]
    if branch:
        parts.append(f"Branch: {branch}")
    if paths:
        parts.append("Files:\n" + "\n".join(f"- {p}" for p in paths))
    hint = (hint or "").strip()
    if hint:
        parts.append("User's current draft (improve or replace):\n" + hint)
    parts.append("Diff:\n" + (diff.strip() or "(no textual diff)"))
    return "\n\n".join(parts)


def _pick_files(status: dict[str, Any], paths: list[str]) -> list[dict[str, Any]]:
    files = [item for item in (status.get("files") or []) if item.get("path")]
    wanted = [p for p in safe_rel_paths(paths) if p]
    if wanted:
        by_path = {str(item["path"]): item for item in files}
        return [by_path[p] for p in wanted if p in by_path][:_MAX_FILES]
    staged = [item for item in files if item.get("staged")]
    return (staged or files)[:_MAX_FILES]


async def collect_commit_context(
    backend: WorkspaceBackend,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    status = await parse_status(backend)
    if not status.get("ok"):
        return {"ok": False, "error": status.get("error") or "not a git repository", "paths": [], "diff": "", "branch": ""}
    picked = _pick_files(status, paths or [])
    chunks: list[str] = []
    used_paths: list[str] = []
    used = 0
    for item in picked:
        path = str(item["path"])
        pieces: list[str] = []
        if item.get("staged"):
            try:
                pieces.append(await file_diff(backend, path, staged=True))
            except Exception:
                pass
        if item.get("unstaged") or str(item.get("code") or "").strip() in {"?", "??"}:
            try:
                pieces.append(await file_diff(backend, path, staged=False))
            except Exception:
                pass
        text = "\n".join(part for part in pieces if part).strip() or f"(changed: {item.get('code') or '?'})"
        if len(text) > _PER_FILE:
            text = text[:_PER_FILE] + "\n… (truncated)"
        remain = _TOTAL - used
        if remain <= 80:
            break
        if len(text) > remain:
            text = text[:remain] + "\n… (truncated)"
        chunks.append(f"### {path}\n{text}")
        used_paths.append(path)
        used += len(text)
        if used >= _TOTAL:
            break
    return {
        "ok": True,
        "branch": str(status.get("branch") or ""),
        "paths": used_paths,
        "diff": "\n\n".join(chunks),
    }
