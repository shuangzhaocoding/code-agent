from __future__ import annotations

from fastapi import HTTPException

from code_agent.db.models import LlmProvider
from code_agent.plugins.base import registry


def require_provider_kind(kind: str) -> None:
    if registry.is_provider_kind_available(kind):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "plugin.disabled",
            "message": f"模型适配插件已停用，无法使用 kind={kind}",
        },
    )


async def require_provider_available(provider: LlmProvider | None) -> LlmProvider:
    if provider is None:
        raise HTTPException(status_code=404, detail={"code": "provider.not_found"})
    if registry.is_provider_kind_available(provider.kind):
        return provider
    raise HTTPException(
        status_code=403,
        detail={
            "code": "plugin.disabled",
            "message": f"模型适配插件已停用，无法使用提供商 {provider.name}（{provider.kind}）",
        },
    )
