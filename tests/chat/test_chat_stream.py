"""POST /api/chat/stream: SSE meta → delta* → done, persistence, error events."""

import json

import httpx
import respx
from app.services import llm as llm_module


def _sse(*chunks: str) -> str:
    return "".join(f"data: {chunk}\n\n" for chunk in chunks)


def _delta(content: str, model: str = "test-model") -> str:
    return json.dumps({"model": model, "choices": [{"delta": {"content": content}}]})


USAGE_CHUNK = json.dumps({"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 3}})


async def test_stream_meta_deltas_done_and_persists(
    client, registered_user, auth_headers, llm_url, parse_sse
):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse(_delta("Hello "), _delta("stream"), USAGE_CHUNK, "[DONE]"),
            headers={"content-type": "text/event-stream"},
        )
        async with client.stream(
            "POST", "/api/chat/stream", headers=auth_headers, json={"content": "Stream it"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = await parse_sse(response)

    kinds = [kind for kind, _ in events]
    assert kinds[0] == "meta"
    assert kinds[-1] == "done"
    assert "error" not in kinds

    meta = events[0][1]
    assert meta["user_message"]["content"] == "Stream it"
    conversation_id = meta["conversation_id"]

    streamed = "".join(data["content"] for kind, data in events if kind == "delta")
    assert streamed == "Hello stream"

    done = events[-1][1]
    assert done["assistant_message"]["role"] == "assistant"
    assert done["assistant_message"]["content"] == "Hello stream"
    assert done["assistant_message"]["tokens"] == 3
    assert done["usage"] == {"prompt_tokens": 5, "completion_tokens": 3}

    detail = await client.get(f"/api/conversations/{conversation_id}", headers=auth_headers)
    roles = [message["role"] for message in detail.json()["messages"]]
    assert roles == ["user", "assistant"]


async def test_stream_error_event_on_llm_failure_keeps_user_message(
    client, registered_user, auth_headers, llm_url, parse_sse, monkeypatch
):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").mock(
            side_effect=[httpx.Response(500)] * 3
        )
        async with client.stream(
            "POST", "/api/chat/stream", headers=auth_headers, json={"content": "fail"}
        ) as response:
            assert response.status_code == 200
            events = await parse_sse(response)

    kinds = [kind for kind, _ in events]
    assert kinds[0] == "meta"
    assert kinds[-1] == "error"
    assert events[-1][1]["error"]["code"] == "llm_unavailable"
    assert not any(kind == "done" for kind in kinds)

    conversation_id = events[0][1]["conversation_id"]
    detail = await client.get(f"/api/conversations/{conversation_id}", headers=auth_headers)
    roles = [message["role"] for message in detail.json()["messages"]]
    assert roles == ["user"]


async def test_stream_requires_authentication(client):
    response = await client.post("/api/chat/stream", json={"content": "hi"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
