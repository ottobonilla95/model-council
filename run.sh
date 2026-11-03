#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci && npm run build)
fi
exec uv run --locked uvicorn parallax.app:app --host 127.0.0.1 --port "${PARALLAX_PORT:-8310}"
