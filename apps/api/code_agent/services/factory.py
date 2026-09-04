from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import RegisterTortoise

from code_agent.agent.checkpointer import checkpointer_lifespan
from code_agent.agent.checkpoint_cleanup import schedule_startup_checkpoint_cleanup
from code_agent.config import settings
from code_agent.crypto import encrypt_secret
from code_agent.db.models import LlmModel, LlmProvider, Setting
from code_agent.db.schema import upgrade_llm_schema
from code_agent.db.sqlite_tuning import configure_tortoise_sqlite
from code_agent.llm.hub import apply_preset, register_builtin_providers
from code_agent.llm.models_sync import sync_provider_models
from code_agent.plugins.loader import apply_plugin_states, load_plugins
from code_agent.runtime.profile import runtime_public, service_mode
from code_agent.storage.backends import resolve_database_url, storage_database_backend, storage_public
from code_agent.storage.events import close_redis
from code_agent.tools.host import register_builtin_tools


ServiceRole = Literal["api", "terminal", "preview", "monolith"]


async def _load_stored_settings() -> None:
    for row in await Setting.all():
        parts = row.key.split(".", 1)
        if len(parts) != 2:
            continue
        settings._cfg.setdefault(parts[0], {})[parts[1]] = row.value_json


async def _seed_llm_from_env() -> None:
    import os

    deepseek_key = os.environ.get("CODE_AGENT_DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if deepseek_key and not await LlmProvider.filter(kind="deepseek").exists():
        await apply_preset("deepseek", api_key=deepseek_key, make_default=True)
        return
    if await LlmProvider.all().count() > 0:
        return
    api_key = os.environ.get("CODE_AGENT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base_url = os.environ.get("CODE_AGENT_OPENAI_BASE_URL") or "https://api.openai.com/v1"
    if not api_key and "11434" not in base_url:
        return
    provider = await LlmProvider.create(
        name="Default",
        kind="openai_compat",
        base_url=base_url.rstrip("/"),
        api_key_encrypted=encrypt_secret(api_key or "ollama"),
    )
    try:
        await sync_provider_models(provider, make_default=True)
    except Exception:
        model_id = os.environ.get("CODE_AGENT_OPENAI_MODEL") or "gpt-4o-mini"
        from code_agent.llm.capabilities import default_params, infer_capabilities

        caps = infer_capabilities(model_id)
        await LlmModel.create(
            provider_id=provider.id,
            model_id=model_id,
            display_name=model_id,
            capabilities_json=caps,
            params_json=default_params(caps),
            is_default=True,
            supports_tools=True,
        )


def create_app(role: ServiceRole = "monolith") -> FastAPI:
    title = {
        "monolith": "Code Agent",
        "api": "Code Agent API",
        "terminal": "Code Agent Terminal",
        "preview": "Code Agent Preview",
    }[role]

    app = FastAPI(title=title, version="0.2.0", lifespan=_lifespan_for(role))

    if role in {"monolith", "api"}:
        _mount_api_routers(app)

    if role == "api":
        _mount_gateway_proxies(app)

    if role == "monolith":
        if service_mode("terminal") == "inline":
            from code_agent.routers import terminals

            app.include_router(terminals.router)
        if service_mode("preview") == "inline":
            from code_agent.routers import preview

            app.include_router(preview.router)
    elif role == "terminal":
        from code_agent.routers import terminals

        app.include_router(terminals.router)
    elif role == "preview":
        from code_agent.routers import preview

        app.include_router(preview.router)

    # monolith + split api-gateway: serve built UI on server.port when dist exists
    if role in {"monolith", "api"}:
        _mount_static_ui(app)

    @app.get("/api/health")
    async def health():
        from code_agent.streaming.run_capacity import active_run_count, max_concurrent_runs

        return {
            "ok": True,
            "name": title,
            "role": role,
            "runtime": runtime_public(),
            "storage": storage_public(),
            "runs": {"active": active_run_count(), "max_concurrent": max_concurrent_runs()},
        }

    return app


def _mount_gateway_proxies(app: FastAPI) -> None:
    terminal_standalone = service_mode("terminal") == "standalone"
    preview_standalone = service_mode("preview") == "standalone"
    if not terminal_standalone and not preview_standalone:
        return
    from code_agent.services.gateway_proxy import create_gateway_proxy_router

    app.include_router(
        create_gateway_proxy_router(terminal=terminal_standalone, preview=preview_standalone)
    )


def _mount_api_routers(app: FastAPI) -> None:
    from code_agent.routers import (
        conversations,
        git,
        llm,
        memories,
        runs,
        settings as settings_router,
        skills,
        uploads,
        workspaces,
    )

    origins = settings.get("server.cors_origins") or [
        "http://127.0.0.1:4061",
        "http://localhost:4061",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(workspaces.router)
    app.include_router(memories.router)
    app.include_router(git.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    app.include_router(llm.router)
    app.include_router(skills.router)
    app.include_router(settings_router.router)
    app.include_router(uploads.router)


def _mount_static_ui(app: FastAPI) -> None:
    static_dir = settings.resolve_static_dir()
    if not static_dir:
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="ui-assets")

    index_file = static_dir / "index.html"

    @app.get("/", include_in_schema=False)
    async def ui_index():
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="UI not built")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def ui_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = static_dir / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="UI not built")


def _lifespan_for(role: ServiceRole):
    need_checkpointer = role in {"monolith", "api"}  # api doesn't need it; worker does

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if role == "monolith":
            async with checkpointer_lifespan():
                async with RegisterTortoise(
                    app,
                    db_url=resolve_database_url(),
                    modules={"models": ["code_agent.db.models"]},
                    generate_schemas=True,
                    _enable_global_fallback=True,
                ):
                    await _startup_common(full=True)
                    yield
                    await close_redis()
            return

        async with RegisterTortoise(
            app,
            db_url=resolve_database_url(),
            modules={"models": ["code_agent.db.models"]},
            generate_schemas=True,
            _enable_global_fallback=True,
        ):
            await _startup_common(full=False)
            try:
                yield
            finally:
                await close_redis()

    return lifespan


async def _startup_common(*, full: bool) -> None:
    register_builtin_providers()
    register_builtin_tools()
    load_plugins()
    await apply_plugin_states()
    await upgrade_llm_schema()
    if storage_database_backend() == "sqlite":
        await configure_tortoise_sqlite()
    await _load_stored_settings()
    if full:
        await _seed_llm_from_env()
        schedule_startup_checkpoint_cleanup()
    host = settings.get("server.host")
    port = settings.get("server.port")
    print(f"Code Agent on {host}:{port} — profile={settings.get('runtime.profile', 'split')}")
