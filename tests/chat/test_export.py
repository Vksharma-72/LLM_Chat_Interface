"""GET /api/conversations/{id}/export — markdown + JSON downloads (S8)."""

import json

import respx

COMPLETION_PAYLOAD = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "the reply"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


async def _create_conversation_with_messages(client, auth_headers, llm_url, title):
    created = await client.post(
        "/api/conversations", headers=auth_headers, json={"title": title}
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        for content in ("first question", "second question"):
            sent = await client.post(
                "/api/chat/send",
                headers=auth_headers,
                json={"conversation_id": conversation_id, "content": content},
            )
            assert sent.status_code == 200
    return conversation_id


async def test_export_markdown_format(
    client, registered_user, auth_headers, llm_url
):
    conversation_id = await _create_conversation_with_messages(
        client, auth_headers, llm_url, "My Exported Chat"
    )

    response = await client.get(
        f"/api/conversations/{conversation_id}/export?format=md", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert 'filename="My-Exported-Chat.md"' in response.headers["content-disposition"]

    body = response.text
    assert body.startswith("# My Exported Chat")
    assert "**User:**\nfirst question" in body
    assert "**Assistant:**\nthe reply" in body
    assert body.count("**User:**") == 2


async def test_export_json_format(client, registered_user, auth_headers, llm_url):
    conversation_id = await _create_conversation_with_messages(
        client, auth_headers, llm_url, "Json Chat"
    )

    response = await client.get(
        f"/api/conversations/{conversation_id}/export?format=json", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]

    data = json.loads(response.text)
    assert data["title"] == "Json Chat"
    assert "exported_at" in data
    assert [m["role"] for m in data["messages"]] == ["user", "assistant", "user", "assistant"]
    assert data["messages"][0]["content"] == "first question"
    assert "id" in data["messages"][0] and "created_at" in data["messages"][0]


async def test_export_defaults_to_markdown(client, registered_user, auth_headers, llm_url):
    conversation_id = await _create_conversation_with_messages(
        client, auth_headers, llm_url, "Default"
    )

    response = await client.get(
        f"/api/conversations/{conversation_id}/export", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")


async def test_export_foreign_conversation_404(client, registered_user, auth_headers, llm_url):
    conversation_id = await _create_conversation_with_messages(
        client, auth_headers, llm_url, "Private"
    )
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    response = await client.get(
        f"/api/conversations/{conversation_id}/export?format=md", headers=other_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_export_unknown_format_422(client, registered_user, auth_headers):
    created = await client.post("/api/conversations", headers=auth_headers, json={})
    conversation_id = created.json()["id"]

    response = await client.get(
        f"/api/conversations/{conversation_id}/export?format=pdf", headers=auth_headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_export_requires_authentication(client):
    created = await client.post("/api/conversations", json={})
    assert created.status_code == 401
