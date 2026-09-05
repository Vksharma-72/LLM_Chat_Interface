"""Users endpoints: get/update me, password change, 30-day usage."""

import uuid
from datetime import UTC, datetime, timedelta

from app.db.repositories import ApiUsageRepository
from app.db.session import get_sessionmaker


async def test_get_me(client, registered_user, auth_headers):
    response = await client.get("/api/users/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == registered_user["user"]


async def test_update_username(client, registered_user, auth_headers):
    response = await client.put(
        "/api/users/me", json={"username": "renamed"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["username"] == "renamed"

    login = await client.post(
        "/api/auth/login", json={"username_or_email": "renamed", "password": "password123"}
    )
    assert login.status_code == 200


async def test_update_username_duplicate_409(client, registered_user, auth_headers):
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    assert other.status_code == 201

    response = await client.put("/api/users/me", json={"username": "other"}, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_username"


async def test_change_password_then_relogin(client, registered_user, auth_headers):
    wrong_current = await client.put(
        "/api/users/me/password",
        json={"current_password": "not-it", "new_password": "newpassword1"},
        headers=auth_headers,
    )
    assert wrong_current.status_code == 401
    assert wrong_current.json()["error"]["code"] == "invalid_credentials"

    changed = await client.put(
        "/api/users/me/password",
        json={"current_password": "password123", "new_password": "newpassword1"},
        headers=auth_headers,
    )
    assert changed.status_code == 204

    old_password = await client.post(
        "/api/auth/login", json={"username_or_email": "user", "password": "password123"}
    )
    assert old_password.status_code == 401

    new_password = await client.post(
        "/api/auth/login", json={"username_or_email": "user", "password": "newpassword1"}
    )
    assert new_password.status_code == 200


async def test_usage_zero_filled_30_days(client, registered_user, auth_headers):
    response = await client.get("/api/users/usage", headers=auth_headers)
    assert response.status_code == 200

    days = response.json()["days"]
    assert len(days) == 30
    today = datetime.now(UTC).date()
    assert days[0]["date"] == (today - timedelta(days=29)).isoformat()
    assert days[-1]["date"] == today.isoformat()
    assert all(day["tokens"] == 0 and day["requests"] == 0 for day in days)


async def test_usage_aggregates_api_usage_rows(client, registered_user, auth_headers):
    user_id = uuid.UUID(registered_user["user"]["id"])
    today = datetime.now(UTC).date()

    async with get_sessionmaker()() as session:
        repo = ApiUsageRepository(session)
        await repo.increment(user_id, tokens=123, requests=2)
        await repo.increment(user_id, tokens=7, requests=1, day=today - timedelta(days=5))
        await session.commit()

    response = await client.get("/api/users/usage", headers=auth_headers)
    assert response.status_code == 200

    days = response.json()["days"]
    assert len(days) == 30
    assert days[-1] == {"date": today.isoformat(), "tokens": 123, "requests": 2}
    assert days[24] == {
        "date": (today - timedelta(days=5)).isoformat(),
        "tokens": 7,
        "requests": 1,
    }
    assert sum(day["tokens"] for day in days) == 130
