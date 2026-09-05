"""Shared pytest fixtures (PROJECT_PLAN.md §12).

Tests ALWAYS run against `llmchat_test` (Postgres) and Redis db 1. The env
overrides below are applied at import time, BEFORE any `app.*` import, so
pydantic-settings sees them (real env vars win over the root `.env` file).
"""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")

# Must happen before importing the app config (E402 ignored via pyproject).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL

import pytest
from app.main import create_app
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def app():
    """The FastAPI app with its lifespan (startup/shutdown) run."""
    application = create_app()
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app):
    """An async HTTP client bound to the app (no real network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
