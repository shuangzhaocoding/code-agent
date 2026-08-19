from __future__ import annotations

THINKING_LEVELS = ("off", "low", "medium", "high")

_BUDGET = {
    "low": 1024,
    "medium": 8192,
    "high": 32768,
}


def normalize_thinking_level(level: str | bool | None) -> str:
    if isinstance(level, bool):
        return "medium" if level else "off"
    if isinstance(level, str) and level in THINKING_LEVELS:
        return level
    return "off"


def thinking_enabled(level: str | bool | None) -> bool:
    return normalize_thinking_level(level) != "off"


def thinking_prompt(level: str | bool | None) -> str:
    normalized = normalize_thinking_level(level)
    if normalized == "off":
        return ""
    if normalized == "low":
        return "- Think lightly only when the step is ambiguous; keep internal reasoning brief."
    if normalized == "high":
        return "- Deep thinking is ON. Reason thoroughly before acting, then execute decisively."
    return "- Think step by step before acting; keep analysis concise."


def _looks_reasoner(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return any(token in name for token in ("reasoner", "thinking")) or name.startswith(("o1", "o3", "o4"))


def thinking_off_extra_body(model_id: str | None) -> dict:
    name = (model_id or "").lower()
    if _looks_reasoner(model_id) or "deepseek" in name:
        return {"thinking": {"type": "disabled"}}
    return {}


def thinking_extra_body(level: str | bool | None, model_id: str | None) -> dict:
    normalized = normalize_thinking_level(level)
    if normalized == "off":
        return {}

    name = (model_id or "").lower()
    budget = _BUDGET.get(normalized, _BUDGET["medium"])

    if _looks_reasoner(model_id):
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    if "deepseek" in name:
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    if name.startswith(("o1", "o3", "o4")):
        return {}

    if normalized == "low":
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


def preferred_reasoner_level(level: str | bool | None) -> str:
    normalized = normalize_thinking_level(level)
    if normalized in {"medium", "high"}:
        return normalized
    return "low"
