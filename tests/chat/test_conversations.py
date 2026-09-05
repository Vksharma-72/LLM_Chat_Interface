"""Conversation CRUD, listing (pagination/pinned/counts), search, ownership."""

import respx


async def _create(client, headers, title=None):
    response = await client.post(
        "/api/conversations", headers=headers, json={"title": title} if title else {}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_get_conversation(client, registered_user, auth_headers):
    created = await _create(client, auth_headers, title="My topic")
    assert created["title"] == "My topic"
    assert created["is_pinned"] is False

    default = await _create(client, auth_headers)
    assert default["title"] == "New Conversation"

    detail = await client.get(f"/api/conversations/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["conversation"]["id"] == created["id"]
    assert detail.json()["messages"] == []


async def test_list_pagination_pinned_first_and_counts(
    client, registered_user, auth_headers, llm_url
):
    older = await _create(client, auth_headers, title="older")
    newer = await _create(client, auth_headers, title="newer")
    pinned = await _create(client, auth_headers, title="pinned")

    await client.patch(
        f"/api/conversations/{pinned['id']}", headers=auth_headers, json={"is_pinned": True}
    )
    # bump updated_at ordering: newer conversation gets a message → most recent
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )
        await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"conversation_id": newer["id"], "content": "give newer activity"},
        )

    listing = await client.get("/api/conversations", headers=auth_headers)
    body = listing.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [pinned["id"], newer["id"], older["id"]]
    counts = {item["id"]: item["message_count"] for item in body["items"]}
    assert counts[newer["id"]] == 2
    assert counts[pinned["id"]] == 0

    page = await client.get(
        "/api/conversations?limit=2&offset=1", headers=auth_headers
    )
    assert [item["id"] for item in page.json()["items"]] == [newer["id"], older["id"]]
    assert page.json()["total"] == 3


async def test_patch_title_and_pin(client, registered_user, auth_headers):
    conversation = await _create(client, auth_headers)

    patched = await client.patch(
        f"/api/conversations/{conversation['id']}",
        headers=auth_headers,
        json={"title": "Renamed", "is_pinned": True},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Renamed"
    assert patched.json()["is_pinned"] is True


async def test_delete_conversation_cascades(client, registered_user, auth_headers, llm_url):
    conversation = await _create(client, auth_headers)
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }
        )
        await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"conversation_id": conversation["id"], "content": "to be deleted"},
        )

    deleted = await client.delete(
        f"/api/conversations/{conversation['id']}", headers=auth_headers
    )
    assert deleted.status_code == 204

    gone = await client.get(f"/api/conversations/{conversation['id']}", headers=auth_headers)
    assert gone.status_code == 404

    listing = await client.get("/api/conversations", headers=auth_headers)
    assert listing.json()["total"] == 0


async def test_foreign_conversation_404_no_existence_leak(client, registered_user, auth_headers):
    conversation = await _create(client, auth_headers, title="secret")

    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    for method, payload in (
        ("GET", None),
        ("PATCH", {"title": "hijack"}),
        ("DELETE", None),
    ):
        response = await client.request(
            method,
            f"/api/conversations/{conversation['id']}",
            headers=other_headers,
            json=payload,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    # other user's list does not see it either
    other_list = await client.get("/api/conversations", headers=other_headers)
    assert other_list.json()["total"] == 0


async def test_search_over_titles_and_message_content(
    client, registered_user, auth_headers, llm_url
):
    await _create(client, auth_headers, title="Quantum physics notes")
    other = await _create(client, auth_headers, title="Groceries")

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "noted"}}],
            }
        )
        await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"conversation_id": other["id"], "content": "remember the entanglement paper"},
        )

    by_title = await client.get("/api/conversations?q=quantum", headers=auth_headers)
    assert [item["title"] for item in by_title.json()["items"]] == ["Quantum physics notes"]

    by_content = await client.get("/api/conversations?q=entanglement", headers=auth_headers)
    assert [item["title"] for item in by_content.json()["items"]] == ["Groceries"]

    none = await client.get("/api/conversations?q=zzz-nothing", headers=auth_headers)
    assert none.json()["items"] == []
    assert none.json()["total"] == 0


async def test_conversations_require_authentication(client):
    response = await client.get("/api/conversations")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
