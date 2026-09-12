from __future__ import annotations

from typing import Any


INLINE_SYSTEM = """You are an inline code editor.
Rewrite ONLY the selected snippet according to the user's instruction.
Return the replacement code only — no markdown fences, no explanation, no surrounding file.
Preserve the original indentation of the selection unless the instruction requires otherwise.
If the instruction cannot be applied, return the original selection unchanged.
"""


def strip_code_fences(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n")


def message_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return "" if content is None else str(content)


def build_inline_prompt(
    *,
    path: str,
    language: str,
    instruction: str,
    selection: str,
    prefix: str = "",
    suffix: str = "",
) -> str:
    lang = (language or "").strip() or "text"
    parts = [
        f"File: {path}",
        f"Language: {lang}",
        f"Instruction: {instruction.strip()}",
    ]
    if prefix.strip():
        parts.append("Code before the selection:\n" + prefix.rstrip("\n"))
    parts.append("Selected code to rewrite:\n" + (selection if selection.endswith("\n") else selection + "\n"))
    if suffix.strip():
        parts.append("Code after the selection:\n" + suffix.lstrip("\n"))
    parts.append("Return only the rewritten selection.")
    return "\n\n".join(parts)
