from __future__ import annotations

from typing import Any

from code_agent.plugins.base import LlmAdapter, registry

_FALLBACK: LlmAdapter | None = None


def _fallback_adapter() -> LlmAdapter:
    global _FALLBACK
    if _FALLBACK is None:
        from code_agent.llm.adapters.openai_compat import OpenAICompatAdapter

        _FALLBACK = OpenAICompatAdapter()
    return _FALLBACK


def get_llm_adapter(provider: Any) -> LlmAdapter:
    """Resolve the plugin adapter for a stored provider row."""
    kind = str(getattr(provider, "kind", "") or "")
    if registry.providers.get(kind) is not None and not registry.is_provider_kind_available(kind):
        raise ValueError(f"LLM adapter plugin disabled for kind={kind}")
    spec = registry.get_provider(kind)
    if spec is not None and spec.adapter is not None:
        return spec.adapter
    return _fallback_adapter()
