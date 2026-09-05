"""S9 hardening: security headers, body-size cap, and no token leakage in logs."""

from httpx import AsyncClient


async def test_security_headers_on_every_response(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


async def test_oversized_body_rejected_with_413(client: AsyncClient):
    # 1 MB cap; send a JSON body larger than that
    big_payload = "x" * 1_100_000
    response = await client.post(
        "/api/auth/register",
        json={"email": f"{big_payload[:50]}@example.com", "username": big_payload},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_normal_sized_requests_pass(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={"email": "bodycap@example.com", "username": "bodycap", "password": "password123"},
    )
    assert response.status_code == 201


async def test_bearer_tokens_never_appear_in_logs(client: AsyncClient, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        response = await client.post(
            "/api/auth/login",
            headers={"Authorization": "Bearer super-secret-token-abc123"},
            json={"username_or_email": "someone", "password": "wrong-password"},
        )
    assert response.status_code in (401, 404, 429)

    logged = caplog.text
    assert "super-secret-token-abc123" not in logged
    assert "Bearer super-secret-token" not in logged
