"""Redis caching of the model list (5 min) and upstream health (30 s)."""

import json

import httpx
import respx
from app.services import llm as llm_module
from app.services.llm import LLMService


async def test_models_cached_5_minutes(llm_url, redis_client):
    service = LLMService(redis=redis_client)
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": [{"id": "m1"}]})
        assert await service.list_models() == ["m1"]
        assert await service.list_models() == ["m1"]
        assert route.call_count == 1

    ttl = await redis_client.ttl("llm:models")
    assert 0 < ttl <= 300
    await service.aclose()


async def test_models_cache_hit_skips_upstream(llm_url, redis_client):
    await redis_client.set("llm:models", json.dumps(["cached-model"]), ex=300)
    service = LLMService(redis=redis_client)
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": [{"id": "m1"}]})
        assert await service.list_models() == ["cached-model"]
        assert not route.called
    await service.aclose()


async def test_health_success_cached_30_seconds(llm_url, redis_client):
    service = LLMService(redis=redis_client)
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": [{"id": "m1"}]})
        assert await service.health() is True
        assert await service.health() is True
        assert route.call_count == 1

    ttl = await redis_client.ttl("llm:health")
    assert 0 < ttl <= 30
    await service.aclose()


async def test_health_unreachable_cached_30_seconds(llm_url, redis_client, monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    service = LLMService(redis=redis_client)
    with respx.mock:
        route = respx.get(f"{llm_url}/models").mock(
            side_effect=[httpx.Response(500)] * 3
        )
        assert await service.health() is False
        assert route.call_count == 3  # retries inside the first health check
        assert await service.health() is False
        assert route.call_count == 3  # second check served from cache
    await service.aclose()


async def test_health_reports_false_on_rate_limit(llm_url, redis_client):
    service = LLMService(redis=redis_client)
    with respx.mock:
        respx.get(f"{llm_url}/models").respond(status_code=429)
        assert await service.health() is False
    await service.aclose()


async def test_health_without_redis_hits_upstream_every_time(llm_url):
    service = LLMService()  # no redis → no caching
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": [{"id": "m1"}]})
        assert await service.health() is True
        assert await service.health() is True
        assert route.call_count == 2
    await service.aclose()
