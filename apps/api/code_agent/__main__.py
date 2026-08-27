from code_agent.config import settings
from code_agent.main import app


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=str(settings.get("server.host") or "127.0.0.1"),
        port=int(settings.get("server.port") or 4060),
    )


if __name__ == "__main__":
    main()
