#!/usr/bin/env bash
# Print pip requirements for the desktop-bundled Python runtime.
# Usage: write-requirements.sh win|unix
set -euo pipefail

TARGET="${1:?usage: write-requirements.sh win|unix}"

python3.11 - <<PY
target = "$TARGET"
deps = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "tortoise-orm>=0.21.0",
    "aiosqlite>=0.20.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "langgraph>=0.2.50",
    "langgraph-checkpoint-sqlite>=2.0.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    "httpx>=0.27.0",
    "pyyaml>=6.0.2",
    "cryptography>=43.0.0",
    "python-multipart>=0.0.12",
    "sse-starlette>=2.1.0",
    "websockets>=13.0",
    "tzdata>=2024.1",
    "asyncssh>=2.14.0",
]
if target == "win":
    # ConPTY / winpty for in-app terminal on Windows.
    deps.append("pywinpty>=2.0.14")
print("\n".join(deps))
PY
