from __future__ import annotations

import argparse
import logging
import os
import sys

from code_agent.config import settings
from code_agent.services.factory import create_app

LIFECYCLE_COMMANDS = frozenset({"start", "stop", "restart", "status", "init-config"})
SERVICE_COMMANDS = frozenset({"monolith", "api", "terminal", "preview", "worker"})


def _run_foreground(service: str) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    host = str(settings.get("server.host") or "127.0.0.1")
    if service == "terminal":
        host = str(settings.get("runtime.terminal.host") or host)
        port = int(settings.get("runtime.terminal.port") or 4062)
    elif service == "preview":
        host = str(settings.get("runtime.preview.host") or host)
        port = int(settings.get("runtime.preview.port") or 4063)
    else:
        port = int(settings.get("server.port") or 4060)

    if service == "worker":
        from code_agent.services.worker import run_worker

        import asyncio

        asyncio.run(run_worker())
        return

    app = create_app(service)  # type: ignore[arg-type]
    uvicorn.run(app, host=host, port=port)


def _handle_init_config(force: bool) -> None:
    from code_agent.config import describe_user_config, ensure_user_config

    path, created = ensure_user_config(force=force)
    if created:
        print("Created:" if not force else "Reset:", path)
        return
    info = describe_user_config(path)
    print("Already exists:", path)
    print(f"  profile={info['profile']}  terminal={info['terminal_mode']}  preview={info['preview_mode']}")
    print(f"  storage: database={info['storage_database']}  events={info['storage_events']}")
    print("  To regenerate from template: code-agent init-config --force")


def _production_mode(args: argparse.Namespace) -> bool:
    if args.prod:
        return True
    return (os.environ.get("CODE_AGENT_ENV") or "").strip().lower() == "production"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-agent",
        description="Code Agent — local AI coding assistant",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="start|stop|restart|status|init-config — or a foreground service name",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Production mode: built UI, no Vite (with start/restart)",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild frontend before production start/restart",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With init-config: regenerate ~/.code-agent/config.yaml",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _run_foreground("monolith")
        return

    if len(argv) == 1 and argv[0] in SERVICE_COMMANDS:
        _run_foreground(argv[0])
        return

    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command

    if command in SERVICE_COMMANDS:
        _run_foreground(command)
        return

    if command == "init-config":
        _handle_init_config(args.force)
        return

    from code_agent.process.manager import restart, start, status, stop

    if command == "start":
        start(production=_production_mode(args), build=args.build)
        return
    if command == "stop":
        stop()
        return
    if command == "restart":
        restart(production=_production_mode(args), build=args.build)
        return
    if command == "status":
        status()
        return

    parser.error(f"unknown command: {command}")


if __name__ == "__main__":
    main()
