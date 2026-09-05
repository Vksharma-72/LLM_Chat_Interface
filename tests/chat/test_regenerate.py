"""Regenerate support on /api/chat/stream + system_prompt passthrough."""

import json

import respx

COMPLETION_BODY = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
}


def _completion(content: str) -> dict:
    payload = json.loads(json.dumps(COMPLETION_BODY))
    payload["choices"][0]["message"]["content"] = content
    payload["usage"] = {"prompt_tokens": 2, "completion_tokens": 1}
    return payload


def _sse(*chunks: str) -> str:
    return "".join(f"data: {chunk}\n\n" for chunk in chunks)


async def _send(client, headers, content, llm_url, reply):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=_completion(reply))
        response = await client.post(
            "/api/chat/send", headers=headers, json={"content": content}
        )
    assert response.status_code == 200, response.text
    return response.json()


async def test_stream_regenerate_replaces_last_assistant_reply(
    client, registered_user, auth_headers, llm_url, parse_sse
):
    exchange = await _send(client, auth_headers, "first question", llm_url, "first reply")
    conversation_id = exchange["conversation"]["id"]

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse(json.dumps({"model": "test-model", "choices": [{"delta": {"content": "second reply"}}]}), "[DONE]"),
            headers={"content-type": "text/event-stream"},
        )
        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers=auth_headers,
            json={"conversation_id": conversation_id, "regenerate": True},
        ) as response:
            assert response.status_code == 200
            events = await parse_sse(response)

    kinds = [kind for kind, _ in events]
    assert kinds[0] == "meta" and kinds[-1] == "done"

    detail = await client.get(f"/api/conversations/{conversation_id}", headers=auth_headers)
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]  # replaced, not appended
    assert messages[0]["content"] == "first question"
    assert messages[1]["content"] == "second reply"


async def test_stream_regenerate_when_last_message_is_user(
    client, registered_user, auth_headers, llm_url, parse_sse, monkeypatch
):
    from app.services import llm as llm_module

    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    created = await client.post("/api/conversations", headers=auth_headers, json={})
    conversation_id = created.json()["id"]
    # a send that fails at the LLM keeps only the user message
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(status_code=500)
        failed = await client.post(
            "/api/chat/send", headers=auth_headers, json={"conversation_id": conversation_id, "content": "unanswered"}
        )
    assert failed.status_code == 502

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content=_sse(json.dumps({"model": "test-model", "choices": [{"delta": {"content": "finally"}}]}), "[DONE]"),
            headers={"content-type": "text/event-stream"},
        )
        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers=auth_headers,
            json={"conversation_id": conversation_id, "regenerate": True},
        ) as response:
            assert response.status_code == 200
            events = await parse_sse(response)

    assert events[-1][0] == "done"
    detail = await client.get(f"/api/conversations/{conversation_id}", headers=auth_headers)
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant"]


async def test_stream_regenerate_empty_conversation_422(client, registered_user, auth_headers):
    created = await client.post("/api/conversations", headers=auth_headers, json={})
    conversation_id = created.json()["id"]

    response = await client.post(
        "/api/chat/stream",
        headers=auth_headers,
        json={"conversation_id": conversation_id, "regenerate": True},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_stream_regenerate_foreign_conversation_404(client, registered_user, auth_headers):
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    created = await client.post("/api/conversations", headers=other_headers, json={})
    conversation_id = created.json()["id"]

    response = await client.post(
        "/api/chat/stream",
        headers=auth_headers,
        json={"conversation_id": conversation_id, "regenerate": True},
    )
    assert response.status_code == 404


async def test_send_rejects_regenerate(client, registered_user, auth_headers):
    response = await client.post(
        "/api/chat/send", headers=auth_headers, json={"regenerate": True}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_send_passes_system_prompt_to_llm(client, registered_user, auth_headers, llm_url):
    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(json=_completion("ok"))
        response = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "hi", "system_prompt": "Be terse"},
        )
    assert response.status_code == 200

    body = json.loads(route.calls.last.request.read())
    assert body["messages"][0] == {"role": "system", "content": "Be terse"}
    assert response.json()["assistant_message"]["metadata"]["system_prompt"] == "Be terse"


async def test_stream_regenerate_requires_conversation_id(client, registered_user, auth_headers):
    response = await client.post(
        "/api/chat/stream", headers=auth_headers, json={"regenerate": True}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
