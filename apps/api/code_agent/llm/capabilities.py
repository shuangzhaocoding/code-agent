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
            "min": 0.05,
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
    # Do not default top_p: many providers reject it. Only send when the user sets it.
    for key in ("temperature", "max_tokens"):
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
    if top_spec.get("supported") and "top_p" in overrides:
        value = overrides.get("top_p")
        if value is not None:
            parsed = float(value)
            # 1 is the API default (no truncation); omit it. Tiny values are often rejected.
            if 0.01 <= parsed < 1:
                out["top_p"] = parsed

    return out


def supports_thinking(capabilities: dict[str, Any] | None) -> bool:
    return bool((capabilities or {}).get("thinking", {}).get("supported"))


DEFAULT_THINKING_LEVELS = [
    {"value": "off", "label": "关闭思考", "description": "不输出思考过程"},
    {"value": "low", "label": "轻量思考", "description": "必要时简短推理"},
    {"value": "medium", "label": "标准思考", "description": "平衡速度与推理深度"},
    {"value": "high", "label": "深度思考", "description": "充分推理后再行动"},
]


def thinking_levels(capabilities: dict[str, Any] | None) -> list[dict[str, str]]:
    spec = (capabilities or {}).get("thinking") or {}
    if not spec.get("supported"):
        return []
    raw = spec.get("levels") or []
    if not raw:
        return list(DEFAULT_THINKING_LEVELS)
    out: list[dict[str, str]] = []
    known = {item["value"]: item for item in DEFAULT_THINKING_LEVELS}
    for item in raw:
        if isinstance(item, str):
            out.append(known.get(item) or {"value": item, "label": item})
        elif isinstance(item, dict) and item.get("value"):
            out.append(
                {
                    "value": str(item["value"]),
                    "label": str(item.get("label") or item["value"]),
                    "description": str(item.get("description") or ""),
                }
            )
    return out


def apply_capability_overrides(caps: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(caps or {})
    if not isinstance(overrides, dict):
        return merged
    merged["overrides"] = dict(overrides)
    for key in ("tools", "vision", "thinking"):
        if key not in overrides:
            continue
        spec = dict(merged.get(key) or {})
        spec["supported"] = bool(overrides[key])
        if key == "thinking" and spec["supported"] and not spec.get("levels"):
            spec["levels"] = [item["value"] for item in DEFAULT_THINKING_LEVELS]
        merged[key] = spec
    return merged


def resolve_capabilities(
    model_id: str,
    remote: dict | None = None,
    plugin_caps: dict | None = None,
    previous: dict | None = None,
) -> dict[str, Any]:
    """Plugin-provided caps win; otherwise infer from the model id. Keep probe + user edits."""
    caps = infer_capabilities(model_id, remote)
    origin = "inferred"
    if isinstance(plugin_caps, dict) and plugin_caps:
        origin = "plugin"
        for key, value in plugin_caps.items():
            if key in {"availability", "overrides", "origin"}:
                continue
            caps[key] = value
    caps["origin"] = origin
    prev = previous if isinstance(previous, dict) else {}
    availability = prev.get("availability")
    if isinstance(availability, dict):
        caps["availability"] = availability
    overrides = prev.get("overrides")
    if isinstance(overrides, dict) and overrides:
        caps = apply_capability_overrides(caps, overrides)
    return caps
