from __future__ import annotations

from typing import Any


def _looks_reasoner(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return any(token in name for token in ("reasoner", "thinking")) or name.startswith(
        ("o1", "o3", "o4")
    )


def _looks_gpt5(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return name.startswith("gpt-5") and "chat" not in name


def rejects_sampling_params(model_id: str | None) -> bool:
    """gpt-5 / o-series reject temperature and top_p (OpenAI returns 400; gateways wrap as 502)."""
    return _looks_reasoner(model_id) or _looks_gpt5(model_id)


def _looks_vision(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return any(
        token in name
        for token in (
            "vision",
            "gpt-4o",
            "gpt-4.1",
            "claude-3",
            "gemini",
            "qwen-vl",
            "qwen2-vl",
            "qwen2.5-vl",
            "llava",
            "pixtral",
            # DeepSeek vision (e.g. deepseek-v4-flash-vision-exp)
            "deepseek-v4-flash-vision",
            "deepseek-vl",
        )
    )


def _looks_no_tools(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    return name.startswith(("o1", "o3-mini")) or "embedding" in name or "whisper" in name


def infer_capabilities(model_id: str, remote: dict | None = None) -> dict[str, Any]:
    """Infer supported runtime parameters for a model id."""
    remote = remote or {}
    reasoner = _looks_reasoner(model_id)
    no_sampling = rejects_sampling_params(model_id)
    vision = bool(remote.get("supports_vision")) or _looks_vision(model_id)
    tools = remote.get("supports_tools")
    if tools is None:
        tools = not _looks_no_tools(model_id)

    caps: dict[str, Any] = {
        "temperature": {
            "supported": not no_sampling,
            "min": 0,
            "max": 2,
            "default": 0.2,
            "step": 0.1,
        },
        "max_tokens": {
            "supported": True,
            "min": 1,
            "max": 128000,
            "default": 16384 if _looks_gpt5(model_id) else 4096,
        },
        "top_p": {
            "supported": not no_sampling,
            "min": 0,
            "max": 1,
            "default": 1,
            "step": 0.05,
        },
        "thinking": {
            "supported": reasoner
            or _looks_gpt5(model_id)
            or any(
                token in (model_id or "").lower()
                for token in ("deepseek", "qwen", "claude", "gemini", "grok")
            ),
            "levels": ["off", "low", "medium", "high"],
        },
        "tools": {"supported": bool(tools)},
        "vision": {"supported": bool(vision)},
    }
    return caps


def default_params(capabilities: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in ("temperature", "max_tokens", "top_p"):
        spec = capabilities.get(key) or {}
        if spec.get("supported") and "default" in spec:
            params[key] = spec["default"]
    return params


def merge_runtime_params(capabilities: dict[str, Any], params: dict[str, Any] | None) -> dict[str, Any]:
    """Build kwargs for ChatOpenAI from capabilities + user overrides."""
    caps = capabilities or {}
    overrides = params or {}
    out: dict[str, Any] = {}

    temp_spec = caps.get("temperature") or {}
    if temp_spec.get("supported"):
        value = overrides.get("temperature", temp_spec.get("default", 0.2))
        if value is not None:
            out["temperature"] = float(value)

    max_spec = caps.get("max_tokens") or {}
    if max_spec.get("supported"):
        value = overrides.get("max_tokens", max_spec.get("default"))
        if value is not None:
            out["max_tokens"] = int(value)

    top_spec = caps.get("top_p") or {}
    if top_spec.get("supported"):
        value = overrides.get("top_p", top_spec.get("default"))
        if value is not None:
            out["top_p"] = float(value)

    return out


def supports_thinking(capabilities: dict[str, Any] | None) -> bool:
    return bool((capabilities or {}).get("thinking", {}).get("supported"))
