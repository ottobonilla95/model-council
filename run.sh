#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci && npm run build)
fi
exec uv run --locked uvicorn council.app:app --host 127.0.0.1 --port "${COUNCIL_PORT:-8310}"
