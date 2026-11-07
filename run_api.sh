#!/usr/bin/env bash
# Lanzar la API REST del Corpus CSJ
set -eu
cd "$(dirname "$0")"

if [ -f "$HOME/.csj_keys" ]; then
    source "$HOME/.csj_keys"
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "Corpus CSJ API"
echo "  host: $HOST"
echo "  port: $PORT"
echo "  docs: http://$HOST:$PORT/docs"
echo "  llave NVIDIA: $([ -n "${NVIDIA_API_KEY:-}" ] && echo OK || echo FALTA)"
echo "  API_KEY: $([ -n "${API_KEY:-}" ] && echo "activa" || echo "abierta (dev)")"
echo ""

exec python3 api.py
