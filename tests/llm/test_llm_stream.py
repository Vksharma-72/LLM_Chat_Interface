"""Streaming gateway: SSE parsing, event shapes, retry and error events."""

import json

import httpx
import respx
from app.services import llm as llm_module


def _sse(*chunks: str) -> str:
    return "".join(f"data: {chunk}\n\n" for chunk in chunks)


def _delta(content: str, model: str = "test-model") -> str:
    return json.dumps({"model": model, "choices": [{"delta": {"content": content}}]})


USAGE_CHUNK = json.dumps(
    {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
)


async def _collect(generator):
    return [event async for event in generator]


async def test_stream_success_events(llm_service, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse(_delta("Hello"), _delta(" world"), USAGE_CHUNK, "[DONE]"),
            headers={"content-type": "text/event-stream"},
        )
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert events[0] == {"type": "delta", "content": "Hello"}
    assert events[1] == {"type": "delta", "content": " world"}
    assert events[2] == {"type": "usage", "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
    assert events[3] == {
        "type": "done",
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        "model": "test-model",
    }


async def test_stream_done_emitted_without_done_marker(llm_service, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse(_delta("Hey")),
            headers={"content-type": "text/event-stream"},
        )
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert [event["type"] for event in events] == ["delta", "done"]
    assert events[-1]["usage"] is None


async def test_stream_malformed_sse_becomes_error_event(llm_service, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse("{not json"),
            headers={"content-type": "text/event-stream"},
        )
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["error"]["code"] == "llm_unavailable"


async def test_stream_429_becomes_rate_limited_event(llm_service, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(status_code=429)
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["error"]["code"] == "llm_rate_limited"


async def test_stream_5xx_retries_then_success(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, content=_sse(_delta("Hi"), "[DONE]")),
            ]
        )
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert [event["type"] for event in events] == ["delta", "done"]
    assert route.call_count == 2


async def test_stream_connect_errors_yield_single_error_event(
    llm_service, llm_url, monkeypatch
):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").mock(
            side_effect=[httpx.ConnectTimeout("down")] * 3
        )
        events = await _collect(
            llm_service.chat_completion_stream([{"role": "user", "content": "hi"}])
        )

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["error"]["code"] == "llm_unavailable"
    assert route.call_count == 3
