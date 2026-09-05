"""POST /api/chat/send: persistence, auto-title, usage, failure semantics."""

import json

import httpx
import respx
from app.db.session import get_sessionmaker
from app.models import Message
from app.services import llm as llm_module
from sqlalchemy import func, select

COMPLETION_PAYLOAD = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "Hello, human!"}}],
    "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
}


def _mock_completion(llm_url: str, content: str = "Hello, human!"):
    payload = json.loads(json.dumps(COMPLETION_PAYLOAD))
    payload["choices"][0]["message"]["content"] = content
    return respx.post(f"{llm_url}/chat/completions").respond(json=payload)


async def test_send_persists_both_messages_and_auto_titles(
    client, registered_user, auth_headers, llm_url
):
    with respx.mock:
        route = _mock_completion(llm_url)
        response = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": "Hello bot"}
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["conversation"]["title"] == "Hello bot"  # auto-titled from first message
    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "Hello bot"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "Hello, human!"
    assert data["assistant_message"]["tokens"] == 3
    assert data["assistant_message"]["metadata"]["model"] == "test-model"
    assert route.call_count == 1

    async with get_sessionmaker()() as session:
        count = (await session.execute(select(func.count()).select_from(Message))).scalar_one()
    assert count == 2


async def test_send_auto_title_truncates_at_60_chars(client, registered_user, auth_headers, llm_url):
    long_content = (
        "This is a fairly long first user message that should be cut at sixty chars!"
    )
    with respx.mock:
        _mock_completion(llm_url)
        response = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": long_content}
        )

    assert response.status_code == 200
    expected = " ".join(long_content.split())[:60]
    assert response.json()["conversation"]["title"] == expected
    assert len(expected) == 60


async def test_send_to_existing_conversation_keeps_title(
    client, registered_user, auth_headers, llm_url
):
    created = await client.post(
        "/api/conversations", headers=auth_headers, json={"title": "My chat"}
    )
    conversation_id = created.json()["id"]

    with respx.mock:
        _mock_completion(llm_url)
        response = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"conversation_id": conversation_id, "content": "again"},
        )

    assert response.status_code == 200
    assert response.json()["conversation"]["title"] == "My chat"
    assert response.json()["conversation"]["id"] == conversation_id

    listing = await client.get("/api/conversations", headers=auth_headers)
    assert listing.json()["items"][0]["message_count"] == 2


async def test_send_usage_incremented(client, registered_user, auth_headers, llm_url):
    with respx.mock:
        _mock_completion(llm_url)
        response = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": "count me"}
        )
    assert response.status_code == 200

    usage = await client.get("/api/users/usage", headers=auth_headers)
    today = usage.json()["days"][-1]
    assert today["tokens"] == 3
    assert today["requests"] == 1


async def test_send_to_foreign_conversation_404(client, registered_user, auth_headers, llm_url):
    with respx.mock:
        _mock_completion(llm_url)
        created = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": "mine"}
        )
    conversation_id = created.json()["conversation"]["id"]

    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    response = await client.post(
        "/api/chat/send",
        headers=other_headers,
        json={"conversation_id": conversation_id, "content": "not mine"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_send_llm_unavailable_502_keeps_user_message(
    client, registered_user, auth_headers, llm_url, monkeypatch
):
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").mock(
            side_effect=[httpx.Response(500)] * 3
        )
        response = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": "will fail"}
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_unavailable"

    listing = await client.get("/api/conversations", headers=auth_headers)
    conversation_id = listing.json()["items"][0]["id"]
    detail = await client.get(
        f"/api/conversations/{conversation_id}", headers=auth_headers
    )
    roles = [message["role"] for message in detail.json()["messages"]]
    assert roles == ["user"]  # user message kept, no orphan assistant row


async def test_send_validation_errors(client, registered_user, auth_headers, llm_url):
    blank = await client.post("/api/chat/send", headers=auth_headers, json={"content": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "validation_error"

    too_long = await client.post(
        "/api/chat/send", headers=auth_headers, json={"content": "x" * 16001}
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "validation_error"

    bad_temperature = await client.post(
        "/api/chat/send", headers=auth_headers, json={"content": "hi", "temperature": 5.0}
    )
    assert bad_temperature.status_code == 422
