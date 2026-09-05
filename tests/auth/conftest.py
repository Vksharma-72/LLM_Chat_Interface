"""Auth test fixtures: real test DB + real Redis db 1, isolated per test (§12).

The app commits per request (`api.deps.get_db`), so transaction-rollback
isolation is not possible here — each test starts from truncated tables and a
flushed Redis db 1. The app's pooled engine is disposed after each test because
pooled asyncpg connections are event-loop bound and pytest-asyncio runs every
test in a fresh loop.
"""

import os

import pytest
from app.db.session import get_engine
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")

_ALL_TABLES = "users, conversations, messages, refresh_tokens, api_usage"


@pytest.fixture(autouse=True)
async def isolated_stores():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {_ALL_TABLES} CASCADE"))
    finally:
        await engine.dispose()

    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()

    yield

    await get_engine().dispose()


@pytest.fixture
async def redis_client():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def registered_user(client):
    """A registered user (first in the truncated DB → admin) with tokens."""
    response = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "username": "user", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
