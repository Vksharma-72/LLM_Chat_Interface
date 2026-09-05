"""Step 1 test gate: GET /health returns 200 {"status": "ok", ...}."""

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


async def test_health_echoes_request_id_header(client: AsyncClient):
    response = await client.get("/health")

    assert response.headers["x-request-id"]


async def test_health_incoming_request_id_is_reused(client: AsyncClient):
    response = await client.get("/health", headers={"X-Request-ID": "test-req-123"})

    assert response.headers["x-request-id"] == "test-req-123"


async def test_cors_allows_configured_origin(client: AsyncClient):
    response = await client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_cors_rejects_unknown_origin(client: AsyncClient):
    response = await client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
