"""Auth negative cases: credentials, duplicates, tokens, validation, flags."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from app.core.config import get_settings


async def _register(client, email: str, username: str, password: str = "password123"):
    return await client.post(
        "/api/auth/register", json={"email": email, "username": username, "password": password}
    )


async def test_wrong_password_401(client, registered_user):
    response = await client.post(
        "/api/auth/login", json={"username_or_email": "user", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_unknown_user_401(client):
    response = await client.post(
        "/api/auth/login", json={"username_or_email": "ghost", "password": "whatever123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_duplicate_email_409_case_insensitive(client, registered_user):
    response = await _register(client, "USER@example.com", "someone-else")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_email"


async def test_duplicate_username_409(client, registered_user):
    response = await _register(client, "other@example.com", "user")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_username"


async def test_registration_disabled_403(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "REGISTRATION_ENABLED", False)
    response = await _register(client, "new@example.com", "new")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_disabled"


async def test_short_password_422_validation_error(client):
    response = await _register(client, "weak@example.com", "weak", password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_invalid_email_422_validation_error(client):
    response = await _register(client, "not-an-email", "badmail")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def _expired_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "type": "access",
            "jti": uuid.uuid4().hex,
            "iat": now - timedelta(minutes=60),
            "exp": now - timedelta(minutes=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALG,
    )


async def test_expired_access_token_401_token_expired(client, registered_user):
    token = _expired_access_token(registered_user["user"]["id"])
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


async def test_garbage_access_token_401_invalid_token(client):
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_missing_authorization_header_401(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_garbage_refresh_token_401(client):
    response = await client.post("/api/auth/refresh", json={"refresh_token": "garbage"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_access_token_rejected_as_refresh(client, registered_user):
    response = await client.post(
        "/api/auth/refresh", json={"refresh_token": registered_user["access_token"]}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_revoked_refresh_token_401(client, registered_user):
    first = await client.post(
        "/api/auth/refresh", json={"refresh_token": registered_user["refresh_token"]}
    )
    assert first.status_code == 200
    replay = await client.post(
        "/api/auth/refresh", json={"refresh_token": registered_user["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_token"
