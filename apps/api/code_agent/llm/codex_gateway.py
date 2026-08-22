from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from code_agent.llm.thinking import reasoning_effort_for_level, thinking_enabled

CODEX_HOST = "aivalux.com"
CODEX_CANONICAL_ORIGIN = "https://www.aivalux.com"
PREFERRED_MODELS = ("gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4")
SKIP_MODEL_TOKENS = (
    "image",
    "realtime",
    "audio",
    "whisper",
    "tts",
    "dall-e",
    "gpt-image",
    "moderation",
    "embedding",
    "transcribe",
)
# The relay is built for Codex CLI; official OpenAI-Python UA is rejected (502).
CODEX_USER_AGENT = "codex"


def is_codex_gateway(provider: Any) -> bool:
    kind = str(getattr(provider, "kind", "") or "").lower()
    if kind == "aivalux":
        return True
    return CODEX_HOST in str(getattr(provider, "base_url", "") or "").lower()


def is_codex_chat_model(model_id: str | None) -> bool:
    name = (model_id or "").lower()
    if not name:
        return False
    return not any(token in name for token in SKIP_MODEL_TOKENS)


def canonicalize_codex_base_url(base_url: str) -> str:
    """Codex uses https://www.aivalux.com (OpenAI client then talks to /v1).

    `new.aivalux.com` is a different frontend and 502s many chat models.
    """
    raw = (base_url or "").strip() or CODEX_CANONICAL_ORIGIN
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("new.aivalux.com") or host.endswith(".aivalux.com") or host == "aivalux.com":
        host = "www.aivalux.com"
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunparse(parsed._replace(scheme="https", netloc=host, path=path, query="", fragment="")).rstrip("/")


def request_headers(extra: dict | None = None) -> dict[str, str]:
    headers = {"User-Agent": CODEX_USER_AGENT}
    if extra:
        headers.update({str(k): str(v) for k, v in extra.items() if v is not None})
    return headers


def preferred_model_id(model_ids: list[str]) -> str | None:
    chat_ids = [mid for mid in model_ids if is_codex_chat_model(mid)]
    for pref in PREFERRED_MODELS:
        if pref in chat_ids:
            return pref
    return chat_ids[0] if chat_ids else None


def chat_runtime_kwargs(model_id: str | None, thinking_level: str = "off") -> dict[str, Any]:
    """Kwargs that mirror a working Codex CLI session against this relay."""
    effort = reasoning_effort_for_level(thinking_level, model_id)
    if effort is None:
        # These models still reason; "off" maps to the cheapest effort, not chat-completions.
        effort = "low" if not thinking_enabled(thinking_level) else "medium"
    return {
        "use_responses_api": True,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        # Responses API only accepts `reasoning={effort, summary}`, not `reasoning_effort`.
        "reasoning": {"effort": effort, "summary": "auto"},
    }
