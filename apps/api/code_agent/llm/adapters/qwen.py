from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.adapters._shared import (
    BASE_CONFIG_SCHEMA,
    compat_chat_cls,
    decrypt_api_key,
    list_models_openai_compat,
    probe_openai_compat,
    standard_auth_headers,
)
from code_agent.llm.capabilities import merge_runtime_params, rejects_sampling_params, supports_thinking
from code_agent.llm.thinking import THINKING_LEVELS, normalize_thinking_level, thinking_enabled

PLUGIN_ID = "builtin.llm.qwen"

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

CONFIG_SCHEMA = dict(BASE_CONFIG_SCHEMA)

PRESETS: list[dict[str, Any]] = [
    {
        "name": "通义千问",
        "kind": "qwen",
        "title": "阿里云 DashScope",
        "base_url": DEFAULT_BASE_URL,
    },
]

KINDS: list[tuple[str, str]] = [("qwen", "通义千问")]

_BUDGET = {"low": 1024, "medium": 8192, "high": 32768}


def normalize_qwen_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return DEFAULT_BASE_URL
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    if "compatible-mode" not in path:
        if path.endswith("/v1"):
            path = f"{path[: -len('/v1')]}/compatible-mode/v1"
        elif path in {"", "/"}:
            path = "/compatible-mode/v1"
        else:
            path = f"{path}/compatible-mode/v1"
    elif not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunparse(parsed._replace(path=path)).rstrip("/")


def _qwen_auth_headers(provider: LlmProvider) -> tuple[str, dict[str, str]]:
    base_url = normalize_qwen_base_url(provider.base_url or "")
    _, headers = standard_auth_headers(provider)
    return base_url, headers


def dashscope_catalog_url(base_url: str) -> str:
    parsed = urlparse(normalize_qwen_base_url(base_url))
    host = parsed.netloc or "dashscope.aliyuncs.com"
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}/api/v1/models"


def _map_dashscope_capabilities(item: dict[str, Any]) -> dict[str, Any]:
    kinds = {str(x) for x in (item.get("capabilities") or [])}
    features = {str(x).replace("_", "-").lower() for x in (item.get("features") or [])}
    modalities = item.get("inference_metadata") or {}
    request_mod = {str(x).lower() for x in (modalities.get("request_modality") or [])}
    info = item.get("model_info") or {}
    vision = "VU" in kinds or "image" in request_mod or "video" in request_mod
    tools = bool(features & {"function-calling", "function-call", "tools"})
    thinking = "Reasoning" in kinds or any(x.lower() == "reasoning" for x in kinds)
    context_window = info.get("context_window") or info.get("max_input_tokens")
    max_out = info.get("max_output_tokens") or info.get("max_tokens")
    caps: dict[str, Any] = {
        "tools": {"supported": tools},
        "vision": {"supported": vision},
        "thinking": {
            "supported": thinking,
            "levels": ["off", "low", "medium", "high"] if thinking else [],
        },
        "audio": {"supported": "audio" in request_mod or "ASR" in kinds or "TTS" in kinds},
        "origin": "plugin",
    }
    if context_window:
        caps["context_window"] = int(context_window)
        caps["max_tokens"] = {
            "supported": True,
            "min": 1,
            "max": int(max_out or context_window),
            "default": min(int(max_out or 8192), 16384),
        }
    caps["modalities"] = {
        "input": list(modalities.get("request_modality") or []),
        "output": list(modalities.get("response_modality") or []),
    }
    return caps


def _dashscope_row(item: dict[str, Any]) -> dict[str, Any] | None:
    model_id = item.get("model") or item.get("id") or item.get("name")
    if not model_id:
        return None
    caps = _map_dashscope_capabilities(item)
    return {
        "model_id": str(model_id),
        "display_name": str(item.get("name") or model_id),
        "remote": item,
        "capabilities": caps,
        "context_window": caps.get("context_window"),
    }


async def list_dashscope_catalog(provider: LlmProvider, headers: dict[str, str]) -> list[dict[str, Any]]:
    url = dashscope_catalog_url(provider.base_url or "")
    auth = {**headers, "Accept": "application/json"}
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        page = 1
        while page <= 20:
            res = await client.get(
                url,
                headers=auth,
                params={"page_no": page, "page_size": 100, "language": "zh-CN"},
            )
            if res.status_code >= 400:
                raise RuntimeError(res.text[:240] or f"HTTP {res.status_code}")
            payload = res.json() if res.content else {}
            output = payload.get("output") if isinstance(payload, dict) else None
            rows = None
            if isinstance(output, dict):
                rows = output.get("models") or output.get("data")
            if rows is None and isinstance(payload, dict):
                rows = payload.get("data") or payload.get("models")
            if not isinstance(rows, list):
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                mapped = _dashscope_row(item)
                if not mapped or mapped["model_id"] in seen:
                    continue
                seen.add(mapped["model_id"])
                models.append(mapped)
            total = 0
            if isinstance(output, dict):
                total = int(output.get("total") or 0)
            if len(rows) < 100 or (total and len(models) >= total):
                break
            page += 1
    if not models:
        raise RuntimeError("DashScope catalog returned no models")
    return models


def _thinking_extra_body(level: str, model_id: str | None) -> dict[str, Any]:
    normalized = normalize_thinking_level(level)
    if normalized == "off":
        return {"enable_thinking": False}
    budget = _BUDGET.get(normalized, _BUDGET["medium"])
    return {"enable_thinking": True, "thinking_budget": budget}


class QwenAdapter:
    kind = "qwen"
    title = "通义千问"
    description = (
        "阿里云 DashScope OpenAI 兼容接口；思考强度通过 extra_body.enable_thinking / thinking_budget 控制，"
        "推理内容在 reasoning_content 字段返回。"
    )
    config_schema = CONFIG_SCHEMA
    presets = PRESETS
    thinking_levels = THINKING_LEVELS

    def normalize_base_url(self, base_url: str) -> str:
        return normalize_qwen_base_url(base_url)

    def create_chat_model(self, provider: LlmProvider, model: LlmModel):
        cls = compat_chat_cls()
        base_url, headers = _qwen_auth_headers(provider)
        kwargs: dict[str, Any] = {
            "model": model.model_id,
            "api_key": decrypt_api_key(provider),
            "base_url": base_url,
            "default_headers": headers,
            "use_responses_api": False,
        }
        kwargs.update(merge_runtime_params(model.capabilities_json, model.params_json))
        if rejects_sampling_params(model.model_id):
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        return cls(**kwargs)

    async def list_models(self, provider: LlmProvider) -> list[dict[str, Any]]:
        base_url, headers = _qwen_auth_headers(provider)
        if base_url != (provider.base_url or "").rstrip("/"):
            provider.base_url = base_url
            await provider.save()
        try:
            return await list_dashscope_catalog(provider, headers)
        except Exception:
            return await list_models_openai_compat(provider, base_url, headers)

    async def probe_model(self, provider: LlmProvider, model_id: str) -> dict[str, Any]:
        base_url, headers = _qwen_auth_headers(provider)
        return await probe_openai_compat(base_url, headers, model_id)

    def apply_thinking(self, chat: Any, provider: LlmProvider, model: LlmModel, level: str):
        extra = dict(getattr(chat, "extra_body", None) or {})
        extra.pop("thinking", None)
        caps = model.capabilities_json or {}
        if thinking_enabled(level) and supports_thinking(caps):
            extra.update(_thinking_extra_body(level, model.model_id))
        else:
            extra.update(_thinking_extra_body("off", model.model_id))
        return chat.model_copy(update={"extra_body": extra or None})


qwen_adapter = QwenAdapter()
