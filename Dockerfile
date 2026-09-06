# Multi-stage build (PROJECT_PLAN.md §13, Docker deployment).
#
# Stage 1 builds the React frontend with Node; stage 2 installs the Python
# backend with uv and receives the built dist. The final image mirrors the
# repo layout because backend/app/core/config.py derives ROOT_DIR as three
# levels above itself:  /srv/llmchat/backend/app/core/config.py → /srv/llmchat

# --- Stage 1: frontend build -------------------------------------------------
FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv installs the locked backend dependencies into a self-contained .venv;
# uv itself is only needed at build time.
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /srv/llmchat

# Dependencies first so Docker layer caching skips reinstall on code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

ENV PATH="/srv/llmchat/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    UPLOAD_DIR=uploads

# Non-root runtime user; uploads/ is the only writable path (volume-mounted).
RUN useradd --create-home appuser \
    && mkdir -p uploads \
    && chown -R appuser:appuser /srv/llmchat
USER appuser

EXPOSE 3001

# Apply pending migrations, then serve API + built frontend on one origin.
CMD ["sh", "-c", "cd backend && alembic upgrade head && cd .. && exec uvicorn --app-dir backend app.main:app --host 0.0.0.0 --port 3001"]
