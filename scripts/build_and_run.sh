#!/usr/bin/env bash
# Production build & run: build frontend, apply migrations, serve everything
# on the single origin http://localhost:3001 (§13).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Building frontend"
(cd frontend && npm ci && npm run build)

echo "==> Applying database migrations"
(cd backend && uv run alembic upgrade head)

echo "==> Starting server on http://127.0.0.1:3001"
export APP_ENV="${APP_ENV:-production}"
exec uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001
