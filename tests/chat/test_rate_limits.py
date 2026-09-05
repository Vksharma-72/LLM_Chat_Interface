"""Rate limits against real Redis: chat 20/min per user, API 120/hour per user."""

import respx

COMPLETION_PAYLOAD = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


async def test_chat_rate_limit_20_per_minute(client, registered_user, auth_headers, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        for _ in range(20):
            response = await client.post(
                "/api/chat/send", headers=auth_headers, json={"content": "hello"}
            )
            assert response.status_code == 200, response.text

        blocked = await client.post(
            "/api/chat/send", headers=auth_headers, json={"content": "one too many"}
        )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.headers["retry-after"] == "60"


async def test_api_rate_limit_120_per_hour(client, registered_user, auth_headers):
    for _ in range(120):
        response = await client.get("/api/users/me", headers=auth_headers)
        assert response.status_code == 200, response.text

    blocked = await client.get("/api/users/me", headers=auth_headers)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.headers["retry-after"] == "3600"


async def test_chat_rate_limit_is_per_user(client, registered_user, auth_headers, llm_url):
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=COMPLETION_PAYLOAD)
        for _ in range(20):
            await client.post("/api/chat/send", headers=auth_headers, json={"content": "hi"})

        # a different user still has their own budget
        other = await client.post(
            "/api/auth/register",
            json={"email": "other@example.com", "username": "other", "password": "password123"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        ok = await client.post(
            "/api/chat/send", headers=other_headers, json={"content": "my turn"}
        )

    assert ok.status_code == 200
