from __future__ import annotations

from typing import Any

from code_agent.llm.adapters.ccx import KINDS as CCX_KINDS, PLUGIN_ID as CCX_ID, ccx_adapter
from code_agent.llm.adapters.deepseek import KINDS as DEEPSEEK_KINDS, PLUGIN_ID as DEEPSEEK_ID, deepseek_adapter
from code_agent.llm.adapters.gateway import KINDS as GATEWAY_KINDS, PLUGIN_ID as GATEWAY_ID, gateway_adapter
from code_agent.llm.adapters.ollama import KINDS as OLLAMA_KINDS, PLUGIN_ID as OLLAMA_ID, ollama_adapter
from code_agent.llm.adapters.openai import KINDS as OPENAI_KINDS, PLUGIN_ID as OPENAI_ID, openai_adapter
from code_agent.llm.adapters.qwen import KINDS as QWEN_KINDS, PLUGIN_ID as QWEN_ID, qwen_adapter
from code_agent.llm.adapters.openai_compat import (
    KINDS as COMPAT_KINDS,
    PLUGIN_ID as COMPAT_ID,
    openai_compat_adapter,
)
from code_agent.plugins.base import PluginInfo, registry
from code_agent.plugins.meta import apply_plugin_meta


def _register_llm_plugin(
    *,
    plugin_id: str,
    title: str,
    description: str,
    adapter,
    kinds: list[tuple[str, str]],
    meta: dict[str, Any] | None = None,
) -> None:
    info = PluginInfo(
        plugin_id=plugin_id,
        source="builtin",
        title=title,
        description=description,
        kind="llm.provider",
        version="1.0.0",
        api=1,
        origin="builtin",
        contributes=("llm.provider",),
    )
    apply_plugin_meta(info, meta=meta)
    registry.register_plugin(info)
    registry.register_llm_adapter(adapter, plugin_id=plugin_id, kinds=kinds)


def register_builtin_llm_plugins() -> None:
    _register_llm_plugin(
        plugin_id=OPENAI_ID,
        title="OpenAI",
        description=openai_adapter.description,
        adapter=openai_adapter,
        kinds=OPENAI_KINDS,
        meta={
            "author": "OpenAI",
            "homepage": "https://platform.openai.com/",
            "repository": "https://github.com/openai/openai-python",
            "license": "MIT",
            "icon": "globe",
            "accent": "#0891b2",
            "keywords": ("openai", "gpt", "llm"),
        },
    )
    _register_llm_plugin(
        plugin_id=DEEPSEEK_ID,
        title="DeepSeek",
        description=deepseek_adapter.description,
        adapter=deepseek_adapter,
        kinds=DEEPSEEK_KINDS,
        meta={
            "author": "DeepSeek",
            "homepage": "https://platform.deepseek.com/",
            "license": "Proprietary",
            "icon": "think",
            "accent": "#4f6bff",
            "keywords": ("deepseek", "reasoner", "llm"),
        },
    )
    _register_llm_plugin(
        plugin_id=QWEN_ID,
        title="通义千问",
        description=qwen_adapter.description,
        adapter=qwen_adapter,
        kinds=QWEN_KINDS,
        meta={
            "author": "Alibaba Cloud",
            "homepage": "https://dashscope.aliyun.com/",
            "repository": "https://github.com/QwenLM/Qwen",
            "license": "Apache-2.0",
            "icon": "think",
            "accent": "#f97316",
            "keywords": ("qwen", "dashscope", "通义", "llm"),
        },
    )
    _register_llm_plugin(
        plugin_id=GATEWAY_ID,
        title="API 中转",
        description=gateway_adapter.description,
        adapter=gateway_adapter,
        kinds=GATEWAY_KINDS,
        meta={
            "icon": "globe",
            "accent": "#7c3aed",
            "keywords": ("gateway", "relay", "中转", "aivalux"),
        },
    )
    _register_llm_plugin(
        plugin_id=CCX_ID,
        title="CCX 网关",
        description=ccx_adapter.description,
        adapter=ccx_adapter,
        kinds=CCX_KINDS,
        meta={
            "author": "BenedictKing",
            "homepage": "https://benedictking.github.io/ccx/",
            "repository": "https://github.com/BenedictKing/ccx",
            "license": "MIT",
            "icon": "globe",
            "accent": "#0ea5e9",
            "keywords": ("ccx", "gateway", "proxy", "responses", "chat"),
        },
    )
    _register_llm_plugin(
        plugin_id=OLLAMA_ID,
        title="Ollama",
        description=ollama_adapter.description,
        adapter=ollama_adapter,
        kinds=OLLAMA_KINDS,
        meta={
            "author": "Ollama",
            "homepage": "https://ollama.com/",
            "repository": "https://github.com/ollama/ollama",
            "license": "MIT",
            "icon": "chip",
            "accent": "#059669",
            "keywords": ("ollama", "local", "llm"),
        },
    )
    _register_llm_plugin(
        plugin_id=COMPAT_ID,
        title="OpenAI 兼容（通用）",
        description=openai_compat_adapter.description,
        adapter=openai_compat_adapter,
        kinds=COMPAT_KINDS,
        meta={
            "icon": "chip",
            "accent": "#64748b",
            "keywords": ("openai-compat", "custom", "llm"),
        },
    )


# Backward-compatible alias
def register_openai_compat_plugin() -> None:
    register_builtin_llm_plugins()
