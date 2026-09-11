#!/usr/bin/env bash
# Bundle python-build-standalone (install_only_stripped) + project deps for Linux/macOS.
# Usage: bundle-python-standalone.sh linux|macos [arch]
#   arch: linux → x86_64 (default)
#         macos → arm64|x86_64 (default: host uname -m, arm64→aarch64 asset)
set -euo pipefail

PLATFORM="${1:?usage: bundle-python-standalone.sh linux|macos [arch]}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DESKTOP="$ROOT/apps/desktop"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

PBS_TAG="${CODE_AGENT_PBS_TAG:-20260901}"
PY_FULL="${CODE_AGENT_PBS_PYTHON:-3.11.16}"
PY_MM="3.11"

case "$PLATFORM" in
  linux)
    ARCH_IN="${2:-x86_64}"
    case "$ARCH_IN" in
      x86_64|amd64) ARCH=x86_64; UV_PLAT=x86_64-unknown-linux-gnu; TRIPLE=x86_64-unknown-linux-gnu ;;
      aarch64|arm64) ARCH=aarch64; UV_PLAT=aarch64-unknown-linux-gnu; TRIPLE=aarch64-unknown-linux-gnu ;;
      *) echo "unsupported linux arch: $ARCH_IN" >&2; exit 1 ;;
    esac
    RUNTIME="$DESKTOP/runtime/python-linux"
    REQ="$DESKTOP/runtime/requirements-linux.txt"
    ;;
  macos)
    HOST_ARCH="$(uname -m 2>/dev/null || echo arm64)"
    ARCH_IN="${2:-$HOST_ARCH}"
    case "$ARCH_IN" in
      arm64|aarch64) ARCH=aarch64; UV_PLAT=aarch64-apple-darwin; TRIPLE=aarch64-apple-darwin ;;
      x86_64|amd64) ARCH=x86_64; UV_PLAT=x86_64-apple-darwin; TRIPLE=x86_64-apple-darwin ;;
      *) echo "unsupported macos arch: $ARCH_IN" >&2; exit 1 ;;
    esac
    RUNTIME="$DESKTOP/runtime/python-macos"
    REQ="$DESKTOP/runtime/requirements-macos.txt"
    ;;
  *)
    echo "platform must be linux or macos" >&2
    exit 1
    ;;
esac

ASSET="cpython-${PY_FULL}+${PBS_TAG}-${TRIPLE}-install_only_stripped.tar.gz"
BASE_URL="${CODE_AGENT_PBS_BASE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}}"
URL="${CODE_AGENT_PBS_URL:-${BASE_URL}/${ASSET}}"
MIRROR_BASE="${CODE_AGENT_PBS_MIRROR:-https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}}"
CACHE="/tmp/code-agent-${ASSET}"

echo "==> Bundling ${PLATFORM} Python ${PY_FULL} (${TRIPLE}) into ${RUNTIME}"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME" "$DESKTOP/runtime"

# Prefer mirror first when GitHub is slow (override with CODE_AGENT_PBS_URL alone).
CANDIDATES=()
if [[ -n "${CODE_AGENT_PBS_URL:-}" ]]; then
  CANDIDATES+=("$URL")
else
  CANDIDATES+=("${MIRROR_BASE}/${ASSET}" "$URL")
fi

cache_ok() {
  [[ -f "$CACHE" ]] && tar -tzf "$CACHE" >/dev/null 2>&1
}

if ! cache_ok; then
  rm -f "$CACHE"
  ok=0
  for url in "${CANDIDATES[@]}"; do
    echo "==> Downloading ${url}"
    if curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 180 \
      -o "$CACHE" "$url" && cache_ok; then
      ok=1
      break
    fi
    echo "==> Download failed or corrupt; trying next source"
    rm -f "$CACHE"
  done
  [[ "$ok" -eq 1 ]] || { echo "failed to download ${ASSET}" >&2; exit 1; }
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$CACHE" -C "$TMP"
# tarball root is usually "python/"
if [[ -d "$TMP/python" ]]; then
  shopt -s dotglob
  mv "$TMP/python"/* "$RUNTIME"/
  shopt -u dotglob
else
  # fallback: first top-level dir
  TOP="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
  shopt -s dotglob
  mv "$TOP"/* "$RUNTIME"/
  shopt -u dotglob
fi

PY_BIN="$RUNTIME/bin/python3"
test -x "$PY_BIN" || chmod +x "$PY_BIN"
test -x "$PY_BIN"

SITE="$RUNTIME/lib/python${PY_MM}/site-packages"
mkdir -p "$SITE"

bash "$SCRIPTS/write-requirements.sh" unix >"$REQ"

echo "==> Installing ${PLATFORM} wheels into site-packages (uv)"
uv pip install \
  --python-platform "$UV_PLAT" \
  --python-version "$PY_MM" \
  --target "$SITE" \
  -r "$REQ"

# Sanity: key packages present
python3.11 - <<PY
from pathlib import Path
root = Path("$SITE")
need = ["fastapi", "uvicorn", "langgraph", "langchain_core", "tortoise", "httpx", "yaml", "cryptography", "tzdata", "asyncssh"]
missing = [n for n in need if not any(root.glob(n + "*"))]
if missing:
    raise SystemExit(f"missing packages in {PLATFORM} bundle: {missing}")
print("site-packages ok:", len(list(root.iterdir())), "entries")
PY

echo "${PY_FULL}+${PBS_TAG}-${TRIPLE}" >"$RUNTIME/.bundle-version"
du -sh "$RUNTIME"
echo "==> ${PLATFORM} Python runtime ready (${ARCH})"
