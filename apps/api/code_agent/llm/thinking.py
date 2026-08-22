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


def _uses_deepseek_thinking(model_id: str | None) -> bool:
    """Only DeepSeek-style chat APIs accept extra_body.thinking.

    Sending it through a GPT/Claude gateway often becomes 502
    `Upstream access forbidden`.
    """
    name = (model_id or "").lower()
    if name.startswith(("o1", "o3", "o4", "gpt-")):
        return False
    return "deepseek" in name or "reasoner" in name


def thinking_off_extra_body(model_id: str | None) -> dict:
    if _uses_deepseek_thinking(model_id):
        return {"thinking": {"type": "disabled"}}
    return {}


def thinking_extra_body(level: str | bool | None, model_id: str | None) -> dict:
    normalized = normalize_thinking_level(level)
    if normalized == "off" or not _uses_deepseek_thinking(model_id):
        return {}
    budget = _BUDGET.get(normalized, _BUDGET["medium"])
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


def preferred_reasoner_level(level: str | bool | None) -> str:
    normalized = normalize_thinking_level(level)
    if normalized in {"medium", "high"}:
        return normalized
    return "low"


def reasoning_effort_for_level(level: str | bool | None, model_id: str | None) -> str | None:
    """Map UI thinking level to OpenAI Responses `reasoning.effort`.

    Codex on AIValux uses `model_reasoning_effort = "xhigh"` with `wire_api = "responses"`.
    """
    name = (model_id or "").lower()
    if not (name.startswith("gpt-5") or name.startswith(("o1", "o3", "o4"))):
        return None
    if "chat" in name and "gpt-5" in name:
        return None
    if not thinking_enabled(level):
        return None
    normalized = normalize_thinking_level(level)
    return {"low": "low", "medium": "medium", "high": "xhigh"}.get(normalized, "medium")
