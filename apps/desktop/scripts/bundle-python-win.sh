#!/usr/bin/env bash
# Bundle a portable Windows CPython + project deps (no system Python required at runtime).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DESKTOP="$ROOT/apps/desktop"
RUNTIME="$DESKTOP/runtime/python-win"
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
python3.11 - <<'PY' >"$REQ"
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
    # Windows embeddable CPython has no system tz database; Tortoise needs this.
    "tzdata>=2024.1",
    # ConPTY / winpty for in-app terminal on Windows.
    "pywinpty>=2.0.14",
    "asyncssh>=2.14.0",
]
print("\n".join(deps))
PY

echo "==> Installing Windows wheels into site-packages (pip; avoid uv sparse-file bug)"
# IMPORTANT: do NOT use `uv pip install --python-platform windows` here.
# uv can materialize corrupt sparse files (e.g. langsmith .../_datetime_parse.py
# with TiB-scale st_size). electron-builder then expands them and fills the disk.
python3.11 -m pip install \
  --disable-pip-version-check \
  --no-warn-script-location \
  --target "$RUNTIME/Lib/site-packages" \
  --platform win_amd64 \
  --implementation cp \
  --python-version 311 \
  --abi cp311 \
  --only-binary=:all: \
  -r "$REQ"

# Fail fast if any file looks like a sparse/corrupt giant (would explode on pack).
python3.11 - <<PY
from pathlib import Path
root = Path("$RUNTIME")
bad = []
for path in root.rglob("*"):
    if not path.is_file():
        continue
    try:
        st = path.stat()
    except OSError:
        continue
    # >50 MiB for any file, or sparse: size >> allocated blocks
    if st.st_size > 50 * 1024 * 1024:
        bad.append((path, st.st_size, st.st_blocks))
    elif st.st_size > 1024 * 1024 and st.st_blocks * 512 < st.st_size // 8:
        bad.append((path, st.st_size, st.st_blocks))
if bad:
    for path, size, blocks in bad[:20]:
        print(f"suspicious file: {path} size={size} blocks={blocks}")
    raise SystemExit(f"Windows Python bundle has {len(bad)} oversized/sparse file(s); aborting")
print("bundle size check ok")
PY

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
