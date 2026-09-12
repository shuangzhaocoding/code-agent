from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

OpKind = Literal["add", "update", "delete"]


class PatchError(ValueError):
    pass


@dataclass
class Hunk:
    old_start: int | None = None
    lines: list[tuple[str, str]] = field(default_factory=list)

    @property
    def old_text(self) -> str:
        return "\n".join(text for tag, text in self.lines if tag in {" ", "-"})

    @property
    def new_text(self) -> str:
        return "\n".join(text for tag, text in self.lines if tag in {" ", "+"})


@dataclass
class FilePatch:
    path: str
    kind: OpKind
    hunks: list[Hunk] = field(default_factory=list)
    add_content: str = ""


_FILE_HEADER = re.compile(
    r"^\*\*\*\s+(Add File|Update File|Delete File):\s*(.+?)\s*$",
    re.IGNORECASE,
)
_BEGIN = re.compile(r"^\*\*\*\s+Begin Patch\s*$", re.IGNORECASE)
_END = re.compile(r"^\*\*\*\s+End Patch\s*$", re.IGNORECASE)
_HUNK_HEADER = re.compile(r"^@@(?:\s+-(\d+)(?:,\d+)?)?")
_UNIFIED_OLD = re.compile(r"^---\s+(?:a/)?(.+?)\s*$")
_UNIFIED_NEW = re.compile(r"^\+\+\+\s+(?:b/)?(.+?)\s*$")


def _unwrap_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _restore_newline(text: str, style: str) -> str:
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if style == "\r\n":
        body = body.replace("\n", "\r\n")
    return body


def parse_patch(text: str, *, default_path: str = "") -> list[FilePatch]:
    raw = _unwrap_fences(text)
    if not raw.strip():
        raise PatchError("empty patch")
    first = next((line for line in raw.splitlines() if line.strip()), "")
    if first.startswith("--- ") or first.startswith("diff --git"):
        return _parse_unified(raw, default_path=default_path)
    return _parse_v4a(raw, default_path=default_path)


def _parse_v4a(raw: str, *, default_path: str = "") -> list[FilePatch]:
    ops: list[FilePatch] = []
    current: FilePatch | None = None
    hunk: Hunk | None = None
    add_lines: list[str] = []

    def flush_hunk() -> None:
        nonlocal hunk
        if current is None or hunk is None:
            hunk = None
            return
        if hunk.lines:
            current.hunks.append(hunk)
        hunk = None

    def flush_file() -> None:
        nonlocal current, add_lines
        flush_hunk()
        if current is None:
            add_lines = []
            return
        if current.kind == "add":
            current.add_content = "\n".join(add_lines)
            if current.add_content and not current.add_content.endswith("\n"):
                current.add_content += "\n"
        if current.path:
            ops.append(current)
        current = None
        add_lines = []

    for line in raw.splitlines():
        if _BEGIN.match(line) or not line.strip() and current is None:
            continue
        if _END.match(line):
            flush_file()
            break
        header = _FILE_HEADER.match(line)
        if header:
            flush_file()
            action = header.group(1).lower()
            path = header.group(2).strip().lstrip("./")
            kind: OpKind = "update"
            if action.startswith("add"):
                kind = "add"
            elif action.startswith("delete"):
                kind = "delete"
            current = FilePatch(path=path, kind=kind)
            continue
        if current is None:
            if default_path and (line.startswith(("+", "-", " ", "@")) or line.startswith("@@")):
                current = FilePatch(path=default_path, kind="update")
            else:
                continue
        if current.kind == "add":
            add_lines.append(line[1:] if line.startswith("+") else line)
            continue
        if current.kind == "delete":
            continue
        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match or line.startswith("@@"):
            flush_hunk()
            start = int(hunk_match.group(1)) if hunk_match and hunk_match.group(1) else None
            hunk = Hunk(old_start=start)
            continue
        if hunk is None:
            hunk = Hunk()
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            hunk.lines.append(("+", line[1:]))
        elif line.startswith("-"):
            hunk.lines.append(("-", line[1:]))
        elif line.startswith(" "):
            hunk.lines.append((" ", line[1:]))
        else:
            hunk.lines.append((" ", line))
    flush_file()
    if not ops:
        raise PatchError("no file operations in patch")
    return ops


def _parse_unified(raw: str, *, default_path: str = "") -> list[FilePatch]:
    ops: list[FilePatch] = []
    current: FilePatch | None = None
    hunk: Hunk | None = None
    pending_old = ""

    def flush_hunk() -> None:
        nonlocal hunk
        if current is not None and hunk is not None and hunk.lines:
            current.hunks.append(hunk)
        hunk = None

    def flush_file() -> None:
        nonlocal current
        flush_hunk()
        if current and current.path:
            if current.kind == "add" and not current.add_content:
                current.add_content = "\n".join(
                    text for hunk in current.hunks for tag, text in hunk.lines if tag in {" ", "+"}
                )
                if current.add_content and not current.add_content.endswith("\n"):
                    current.add_content += "\n"
                current.hunks = []
            ops.append(current)
        current = None

    for line in raw.splitlines():
        if line.startswith("diff --git"):
            flush_file()
            continue
        old_match = _UNIFIED_OLD.match(line)
        if old_match:
            flush_file()
            pending_old = old_match.group(1).strip()
            continue
        new_match = _UNIFIED_NEW.match(line)
        if new_match:
            new_path = new_match.group(1).strip()
            old_path = pending_old
            pending_old = ""
            if new_path == "/dev/null":
                path = old_path if old_path != "/dev/null" else default_path
                current = FilePatch(path=path, kind="delete")
            elif old_path == "/dev/null":
                current = FilePatch(path=new_path, kind="add")
            else:
                current = FilePatch(path=new_path or old_path or default_path, kind="update")
            continue
        if current is None:
            continue
        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            flush_hunk()
            start = int(hunk_match.group(1)) if hunk_match.group(1) else None
            hunk = Hunk(old_start=start)
            continue
        if hunk is None:
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            hunk.lines.append(("+", line[1:]))
        elif line.startswith("-"):
            hunk.lines.append(("-", line[1:]))
        elif line.startswith(" "):
            hunk.lines.append((" ", line[1:]))
    flush_file()
    if not ops:
        if default_path:
            return _parse_v4a(raw, default_path=default_path)
        raise PatchError("no file operations in patch")
    return ops


def _find_span(haystack: str, needle: str, *, hint: int | None = None) -> int:
    if needle == "":
        return 0 if hint is None else max(0, hint)
    idx = haystack.find(needle)
    if idx >= 0 and haystack.find(needle, idx + 1) < 0:
        return idx
    if hint is not None:
        lines = haystack.split("\n")
        start_line = max(0, hint - 1)
        prefix = "\n".join(lines[:start_line])
        offset = len(prefix) + (1 if prefix else 0)
        idx = haystack.find(needle, offset)
        if idx >= 0:
            return idx
        window = haystack[max(0, offset - 400) : offset + len(needle) + 800]
        local = window.find(needle)
        if local >= 0:
            return max(0, offset - 400) + local
    if idx >= 0:
        return idx
    stripped_hay = "\n".join(line.rstrip() for line in haystack.split("\n"))
    stripped_needle = "\n".join(line.rstrip() for line in needle.split("\n"))
    idx = stripped_hay.find(stripped_needle)
    if idx >= 0:
        # Map stripped index back approximately by walking original lines.
        return _map_stripped_index(haystack, idx)
    raise PatchError("hunk context not found in file")


def _map_stripped_index(haystack: str, stripped_idx: int) -> int:
    raw_pos = 0
    stripped_pos = 0
    for line in haystack.split("\n"):
        kept = line.rstrip()
        if stripped_pos + len(kept) >= stripped_idx:
            return raw_pos + max(0, stripped_idx - stripped_pos)
        stripped_pos += len(kept) + 1
        raw_pos += len(line) + 1
    return max(0, raw_pos - 1)


def apply_hunks(original: str, hunks: list[Hunk]) -> str:
    style = _detect_newline(original)
    body = original.replace("\r\n", "\n").replace("\r", "\n")
    for hunk in hunks:
        old = hunk.old_text
        new = hunk.new_text
        if old == new:
            continue
        hint = None
        if hunk.old_start:
            lines = body.split("\n")
            before = "\n".join(lines[: max(0, hunk.old_start - 1)])
            hint = len(before) + (1 if before else 0)
        if old == "":
            insert_at = hint if hint is not None else len(body)
            prefix = ""
            if insert_at > 0 and not body.endswith("\n") and insert_at >= len(body):
                prefix = "\n"
            body = body[:insert_at] + prefix + new + body[insert_at:]
            continue
        idx = _find_span(body, old, hint=hint)
        body = body[:idx] + new + body[idx + len(old) :]
    if original.endswith(("\n", "\r\n")) and body and not body.endswith("\n"):
        body += "\n"
    return _restore_newline(body, style)


def apply_file_patch(original: str | None, op: FilePatch) -> str | None:
    if op.kind == "delete":
        return None
    if op.kind == "add":
        content = op.add_content
        if content and not content.endswith("\n"):
            content += "\n"
        return content
    if original is None:
        raise PatchError(f"file not found: {op.path}")
    return apply_hunks(original, op.hunks)
