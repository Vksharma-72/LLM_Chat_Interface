"""LLM gateway test fixtures (PROJECT_PLAN.md §12).

Upstream HTTP is respx-mocked; Redis db 1 is real and flushed per test for
the cache tests. `LLM_MODEL` is patched to a fixed value so most tests don't
need an extra /models round-trip; the model-resolution tests override it.
"""

import os

import pytest
from app.core.config import get_settings
from app.services.llm import LLMService
from redis.asyncio import Redis

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture(autouse=True)
async def _flush_test_redis():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def redis_client():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def llm_url() -> str:
    return get_settings().LLM_API_URL


@pytest.fixture
async def llm_service(monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_MODEL", "test-model")
    service = LLMService()
    yield service
    await service.aclose()
