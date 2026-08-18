from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import RegisterTortoise

from code_agent.config import settings
from code_agent.crypto import encrypt_secret
from code_agent.db.models import LlmModel, LlmProvider
from code_agent.llm.hub import register_builtin_providers
from code_agent.plugins.loader import load_plugins
from code_agent.routers import conversations, git, llm, runs, settings as settings_router, skills, terminals, workspaces
from code_agent.tools.host import register_builtin_tools

async def _seed_llm_from_env() -> None:
    import os

    from code_agent.llm.hub import apply_preset

    deepseek_key = os.environ.get("CODE_AGENT_DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if deepseek_key and not await LlmProvider.filter(kind="deepseek").exists():
        await apply_preset("deepseek", api_key=deepseek_key, make_default=True)
        return
    if await LlmProvider.all().count() > 0:
        return
    api_key = os.environ.get("CODE_AGENT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base_url = os.environ.get("CODE_AGENT_OPENAI_BASE_URL") or "https://api.openai.com/v1"
    model_id = os.environ.get("CODE_AGENT_OPENAI_MODEL") or "gpt-4o-mini"
    if not api_key and "11434" not in base_url:
        return
    provider = await LlmProvider.create(
        name="Default",
        kind="openai_compat",
        base_url=base_url.rstrip("/"),
        api_key_encrypted=encrypt_secret(api_key or "ollama"),
    )
    await LlmModel.create(
        provider_id=provider.id,
        model_id=model_id,
        display_name=model_id,
        is_default=True,
        supports_tools=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with RegisterTortoise(
        app,
        db_url=settings.db_url,
        modules={"models": ["code_agent.db.models"]},
        generate_schemas=True,
        _enable_global_fallback=True,
    ):
        register_builtin_providers()
        register_builtin_tools()
        load_plugins()
        await _seed_llm_from_env()
        print(f"Code Agent API on {settings.get('server.host')}:{settings.get('server.port')}")
        print("Default bind is localhost. Do not expose an unauthenticated instance to the internet.")
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="Code Agent", version="0.1.0", lifespan=lifespan)
    origins = settings.get("server.cors_origins") or ["http://127.0.0.1:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(workspaces.router)
    app.include_router(git.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    app.include_router(llm.router)
    app.include_router(skills.router)
    app.include_router(settings_router.router)
    app.include_router(terminals.router)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "name": "Code Agent"}

    return app


app = create_app()
