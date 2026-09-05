"""Full auth flow: register → login → me → refresh (rotation) → logout."""


async def _register(client, email: str, username: str, password: str = "password123"):
    return await client.post(
        "/api/auth/register", json={"email": email, "username": username, "password": password}
    )


async def test_full_auth_flow(client):
    # register → 201 AuthResponse; first user in the truncated DB becomes admin
    response = await _register(client, "Flow@Example.com", "flow")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "flow@example.com"  # lowercased
    assert body["user"]["username"] == "flow"
    assert body["user"]["is_admin"] is True
    access, refresh = body["access_token"], body["refresh_token"]

    # me with the access token
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json() == body["user"]

    # login works with both username and email
    login = await client.post(
        "/api/auth/login", json={"username_or_email": "flow", "password": "password123"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == body["user"]["id"]
    login_email = await client.post(
        "/api/auth/login", json={"username_or_email": "FLOW@example.com", "password": "password123"}
    )
    assert login_email.status_code == 200

    # refresh rotates: new tokens, old refresh token is now rejected
    rotated = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200
    rotated_body = rotated.json()
    assert rotated_body["refresh_token"] != refresh
    assert rotated_body["token_type"] == "bearer"
    new_access, new_refresh = rotated_body["access_token"], rotated_body["refresh_token"]

    replay = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_token"

    me2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me2.status_code == 200

    # logout revokes the current refresh token
    out = await client.post("/api/auth/logout", json={"refresh_token": new_refresh})
    assert out.status_code == 204
    dead = await client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert dead.status_code == 401
    assert dead.json()["error"]["code"] == "invalid_token"


async def test_first_user_is_admin_flag(client):
    first = await _register(client, "first@example.com", "first")
    second = await _register(client, "second@example.com", "second")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["user"]["is_admin"] is True
    assert second.json()["user"]["is_admin"] is False


async def test_me_requires_authentication(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
