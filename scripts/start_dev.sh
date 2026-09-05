#!/usr/bin/env bash
# Dev stack: mock LLM (:8001) + backend with reload (:3001) + Vite dev (:5173).
# Press Ctrl+C once to stop everything.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Starting mock LLM on :8001 (LLM for dev/E2E)"
uv run python scripts/mock_llm_server.py &
MOCK_PID=$!

echo "==> Starting backend on :3001 (LLM_API_URL -> mock)"
LLM_API_URL="${LLM_API_URL:-http://localhost:8001/v1}" \
  uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001 --reload &
BACKEND_PID=$!

echo "==> Starting Vite dev server on :5173 (proxies /api -> :3001)"
cd frontend && npm run dev &
VITE_PID=$!

trap 'kill "$MOCK_PID" "$BACKEND_PID" "$VITE_PID" 2>/dev/null || true' EXIT
echo
echo "Dev stack running:  app http://localhost:5173  |  API http://localhost:3001"
echo "Press Ctrl+C to stop."
wait
