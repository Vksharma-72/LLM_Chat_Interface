"""LLM gateway core behavior: models, completions, retries, error mapping."""

import json

import httpx
import pytest
import respx
from app.core.config import get_settings
from app.services import llm as llm_module
from app.services.llm import LLMBadResponse, LLMRateLimited, LLMUnavailable

COMPLETION_PAYLOAD = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "test-model",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
}


async def test_list_models_success(llm_service, llm_url):
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(
            json={"data": [{"id": "ornithopter-35b"}, {"id": "second"}]}
        )
        models = await llm_service.list_models()

    assert models == ["ornithopter-35b", "second"]
    assert route.call_count == 1


async def test_bearer_header_sent_only_when_key_set(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_API_KEY", "sekrit")
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": []})
        await llm_service.list_models()
        assert route.calls.last.request.headers["Authorization"] == "Bearer sekrit"


async def test_no_bearer_header_without_key(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_API_KEY", "")
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(json={"data": []})
        await llm_service.list_models()
        assert "Authorization" not in route.calls.last.request.headers


async def test_chat_completion_success(llm_service, llm_url):
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        result = await llm_service.chat_completion(
            [{"role": "user", "content": "hi"}], system_prompt="be brief"
        )

    assert result == {
        "content": "Hello",
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
        "model": "test-model",
    }
    body = json.loads(route.calls.last.request.read())
    assert body["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    assert body["stream"] is False
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 1024


async def test_system_prompt_omitted_when_blank(llm_service, llm_url):
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(
            json={"choices": [{"message": {"content": "ok"}}], "model": "test-model"}
        )
        result = await llm_service.chat_completion(
            [{"role": "user", "content": "hi"}], system_prompt="   "
        )

    body = json.loads(route.calls.last.request.read())
    assert all(message["role"] != "system" for message in body["messages"])
    assert result["usage"] is None  # upstream reported no usage


async def test_model_resolution_prefers_settings_then_models(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_MODEL", "preferred")
    with respx.mock:
        models_route = respx.get(f"{llm_url}/models").respond(json={"data": [{"id": "first"}]})
        route = respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        await llm_service.chat_completion([{"role": "user", "content": "hi"}])

    body = json.loads(route.calls.last.request.read())
    assert body["model"] == "preferred"
    assert not models_route.called


async def test_model_resolution_falls_back_to_first_model(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_MODEL", "")
    with respx.mock:
        models_route = respx.get(f"{llm_url}/models").respond(
            json={"data": [{"id": "first-model"}, {"id": "other"}]}
        )
        route = respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        await llm_service.chat_completion([{"role": "user", "content": "hi"}])

    assert json.loads(route.calls.last.request.read())["model"] == "first-model"
    assert models_route.call_count == 1


async def test_timeout_retry_then_success(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").mock(
            side_effect=[httpx.ConnectTimeout("boom"), httpx.Response(200, json=COMPLETION_PAYLOAD)]
        )
        result = await llm_service.chat_completion([{"role": "user", "content": "hi"}])

    assert result["content"] == "Hello"
    assert route.call_count == 2


async def test_5xx_retries_then_llm_unavailable(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        route = respx.get(f"{llm_url}/models").mock(
            side_effect=[httpx.Response(500), httpx.Response(502), httpx.Response(503)]
        )
        with pytest.raises(LLMUnavailable):
            await llm_service.list_models()

    assert route.call_count == 3


async def test_429_passthrough_without_retry(llm_service, llm_url):
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(status_code=429)
        with pytest.raises(LLMRateLimited):
            await llm_service.list_models()

    assert route.call_count == 1


async def test_4xx_maps_to_bad_response_without_retry(llm_service, llm_url):
    with respx.mock:
        route = respx.get(f"{llm_url}/models").respond(status_code=400)
        with pytest.raises(LLMBadResponse):
            await llm_service.list_models()

    assert route.call_count == 1


async def test_malformed_models_payload(llm_service, llm_url):
    with respx.mock:
        respx.get(f"{llm_url}/models").respond(json={"nope": True})
        with pytest.raises(LLMBadResponse):
            await llm_service.list_models()


async def test_malformed_completion_payload(llm_service, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json={"choices": []})
        with pytest.raises(LLMBadResponse):
            await llm_service.chat_completion([{"role": "user", "content": "hi"}])
