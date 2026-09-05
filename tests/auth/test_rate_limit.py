"""Login rate limiting: RATE_LIMIT_LOGIN_PER_15MIN per IP+identifier, real Redis."""


async def test_login_rate_limit_429_with_retry_after(client, registered_user):
    # 5 wrong-password attempts are allowed through (each returns 401)...
    for _ in range(5):
        response = await client.post(
            "/api/auth/login", json={"username_or_email": "user", "password": "wrong-password"}
        )
        assert response.status_code == 401
    # ...the 6th attempt — even with correct credentials — is blocked.
    blocked = await client.post(
        "/api/auth/login", json={"username_or_email": "user", "password": "password123"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.headers["retry-after"] == "900"


async def test_rate_limit_is_per_identifier(client, registered_user):
    for _ in range(5):
        response = await client.post(
            "/api/auth/login", json={"username_or_email": "other-guy", "password": "wrong-password"}
        )
        assert response.status_code == 401

    ok = await client.post(
        "/api/auth/login", json={"username_or_email": "user", "password": "password123"}
    )
    assert ok.status_code == 200


async def test_rate_limit_window_key_has_ttl(client, redis_client):
    for _ in range(6):
        await client.post(
            "/api/auth/login", json={"username_or_email": "ghost", "password": "whatever123"}
        )

    keys = [key async for key in redis_client.scan_iter("login_rl:*")]
    assert len(keys) == 1
    ttl = await redis_client.ttl(keys[0])
    assert 0 < ttl <= 900
