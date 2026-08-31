#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then cp .env.example .env; fi

python3 -m venv .venv
. .venv/bin/activate
pip install -r apps/server/requirements.txt
(cd apps/web && npm install)

uvicorn apps.server.app.main:app --reload --port 8000 &
SERVER_PID=$!
(cd apps/web && npm run dev) &
WEB_PID=$!
trap 'kill $SERVER_PID $WEB_PID 2>/dev/null || true' EXIT
wait
