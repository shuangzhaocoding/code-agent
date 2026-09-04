#!/usr/bin/env bash
# Backward-compatible wrapper — prefer: code-agent start|stop|restart
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMD="${1:-up}"
shift || true
cd "$ROOT/apps/api"
case "$CMD" in
  up) exec python3.11 -m code_agent start "$@" ;;
  down) exec python3.11 -m code_agent stop "$@" ;;
  restart) exec python3.11 -m code_agent restart "$@" ;;
  *)
    echo "Usage: $0 up|down|restart  (or use: code-agent start|stop|restart)"
    exit 1
    ;;
esac
