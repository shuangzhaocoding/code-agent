#!/usr/bin/env bash
# Bundle a portable Windows CPython + project deps (no system Python required at runtime).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DESKTOP="$ROOT/apps/desktop"
RUNTIME="$DESKTOP/runtime/python-win"
API="$ROOT/apps/api"
PY_VER="${CODE_AGENT_WIN_PYTHON_VERSION:-3.11.9}"
EMBED_URL="${CODE_AGENT_WIN_PYTHON_URL:-https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-amd64.zip}"
CACHE="/tmp/code-agent-python-${PY_VER}-embed-amd64.zip"

echo "==> Bundling Windows Python ${PY_VER} into ${RUNTIME}"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"

if [[ ! -f "$CACHE" ]]; then
  echo "==> Downloading ${EMBED_URL}"
  curl -fL --retry 3 --connect-timeout 30 --max-time 300 -o "$CACHE" "$EMBED_URL"
fi
unzip -q -o "$CACHE" -d "$RUNTIME"

PTH="$(ls "$RUNTIME"/python*._pth | head -1)"
cat >"$PTH" <<'EOF'
python311.zip
.
Lib/site-packages
import site
EOF

mkdir -p "$RUNTIME/Lib/site-packages"

REQ="$DESKTOP/runtime/requirements-win.txt"
bash "$DESKTOP/scripts/write-requirements.sh" win >"$REQ"

echo "==> Installing Windows wheels into site-packages (uv cross-platform)"
uv pip install \
  --python-platform x86_64-pc-windows-msvc \
  --python-version 3.11 \
  --target "$RUNTIME/Lib/site-packages" \
  -r "$REQ"

# Ensure package import path for code_agent (shipped under resources/code-agent/apps/api)
MARKER="$RUNTIME/Lib/site-packages/code_agent_desktop.pth"
cat >"$MARKER" <<'EOF'
# Filled at runtime via PYTHONPATH; kept as documentation marker.
EOF

# Sanity: key packages present
python3.11 - <<PY
from pathlib import Path
root = Path("$RUNTIME") / "Lib" / "site-packages"
need = ["fastapi", "uvicorn", "langgraph", "langchain_core", "tortoise", "httpx", "yaml", "cryptography", "tzdata", "winpty"]
missing = [n for n in need if not any(root.glob(n + "*"))]
if missing:
    raise SystemExit(f"missing packages in windows bundle: {missing}")
print("site-packages ok:", len(list(root.iterdir())), "entries")
PY

# Keep marker of python binary for Electron
test -f "$RUNTIME/python.exe"
echo "$PY_VER" >"$RUNTIME/.bundle-version"
du -sh "$RUNTIME"
echo "==> Windows Python runtime ready"
