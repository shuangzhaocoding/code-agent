from __future__ import annotations

import re
from typing import Any

_REMEMBER_HINT = re.compile(
    r"记住|记得|别忘了|请记|帮我记|remember\s+me|remember\s+that|don't\s+forget|keep\s+in\s+mind",
    re.I,
)

_NAME_PATTERNS = [
    re.compile(r"我是\s*[「\"']?([^「」\"'\s，。,!！?？]+)", re.I),
    re.compile(r"我叫\s*[「\"']?([^「」\"'\s，。,!！?？]+)", re.I),
    re.compile(r"叫我\s*[「\"']?([^「」\"'\s，。,!！?？]+)", re.I),
    re.compile(r"my\s+name\s+is\s+([A-Za-z][A-Za-z0-9_-]*)", re.I),
    re.compile(r"call\s+me\s+([A-Za-z][A-Za-z0-9_-]*)", re.I),
    re.compile(r"i\s*['']?m\s+([A-Za-z][A-Za-z0-9_-]*)", re.I),
]

_ROLE_PATTERNS = [
    re.compile(r"我是(?:一名|个)?(.{2,24}?)(?:工程师|开发|设计师|测试|产品)", re.I),
    re.compile(r"i\s*['']?m\s+a\s+([A-Za-z][\w\s-]{2,40})", re.I),
]


def _wants_remember(text: str) -> bool:
    return bool(_REMEMBER_HINT.search(text))


def _extract_name(text: str) -> str | None:
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = (m.group(1) or "").strip("「」\"'，。,. ")
            if name and len(name) <= 40:
                return name
    return None


def _extract_role(text: str) -> str | None:
    for pat in _ROLE_PATTERNS:
        m = pat.search(text)
        if m:
            role = (m.group(1) or "").strip()
            if role:
                return role
    return None


def heuristic_memories(conversation_text: str) -> list[dict[str, Any]]:
    """Fast path for explicit remember-me / profile statements."""
    text = (conversation_text or "").strip()
    if not text:
        return []

    items: list[dict[str, Any]] = []
    user_lines = [ln for ln in text.splitlines() if ln.lower().startswith("user:")]
    blob = "\n".join(user_lines) if user_lines else text

    remember = _wants_remember(blob) or _wants_remember(text)
    name = _extract_name(blob) or _extract_name(text)
    role = _extract_role(blob) or _extract_role(text)

    if name and (remember or "我是" in blob or "我叫" in blob or "叫我" in blob or "my name" in blob.lower()):
        items.append(
            {
                "kind": "profile",
                "subject": "用户称呼",
                "statement": f"用户希望被称呼为 {name}。",
                "tags": ["profile", "user", "name"],
            }
        )

    if role and remember:
        items.append(
            {
                "kind": "profile",
                "subject": "用户角色",
                "statement": f"用户角色：{role}。",
                "tags": ["profile", "user", "role"],
            }
        )

    if remember and not items:
        # Generic remember request without parseable name — still flag for LLM follow-up
        snippet = blob[:200].replace("user:", "").strip()
        if snippet:
            items.append(
                {
                    "kind": "preference",
                    "subject": "用户嘱托",
                    "statement": snippet[:300],
                    "tags": ["remember"],
                }
            )

    return items
