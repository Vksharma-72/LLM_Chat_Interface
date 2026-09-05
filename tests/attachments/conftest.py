"""Attachment test fixtures — same isolation scheme as tests/chat (§12/§15)."""

import io
import os

import pytest
from app.core.config import get_settings
from app.db.session import get_engine
from app.services.llm import LLMService, get_llm_service
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")

_ALL_TABLES = (
    "users, conversations, messages, refresh_tokens, api_usage, attachments"
)


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


@pytest.fixture(autouse=True)
async def chat_llm(app, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_MODEL", "test-model")
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    service = LLMService(redis=redis)
    app.dependency_overrides[get_llm_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_llm_service, None)
    await service.aclose()
    await redis.aclose()


@pytest.fixture
def llm_url() -> str:
    return get_settings().LLM_API_URL


@pytest.fixture
async def registered_user(client):
    response = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "username": "user", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest.fixture
def parse_sse():
    async def _parse(response) -> list[tuple[str, dict]]:
        import json

        events: list[tuple[str, dict]] = []
        current: str | None = None
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("event:"):
                current = line[len("event:") :].strip()
            elif line.startswith("data:") and current:
                events.append((current, json.loads(line[len("data:") :].strip())))
        return events

    return _parse


def png_bytes(color: str = "red", size: int = 8) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()
