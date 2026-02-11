"""Integration tests for /api/v1/heartbeats endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.main import app
from monitoring.database import get_db


async def _client(test_db: AsyncSession) -> AsyncClient:
    async def _override():
        yield test_db
    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.integration
async def test_create_heartbeat(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        resp = await c.post("/api/v1/heartbeats/", json={
            "name": "Nightly Job",
            "expected_interval_seconds": 86400,
        })
    app.dependency_overrides.clear()
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Nightly Job"
    assert data["last_heartbeat_at"] is None


@pytest.mark.integration
async def test_list_heartbeats(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        await c.post("/api/v1/heartbeats/", json={"name": "J1", "expected_interval_seconds": 60})
        resp = await c.get("/api/v1/heartbeats/")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.integration
async def test_ping_heartbeat(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        create = await c.post("/api/v1/heartbeats/", json={"name": "J", "expected_interval_seconds": 60})
        pid = create.json()["public_id"]
        resp = await c.post(f"/api/v1/heartbeats/{pid}/ping")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["last_heartbeat_at"] is not None


@pytest.mark.integration
async def test_delete_heartbeat(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        create = await c.post("/api/v1/heartbeats/", json={"name": "Del", "expected_interval_seconds": 60})
        pid = create.json()["public_id"]
        resp = await c.delete(f"/api/v1/heartbeats/{pid}")
    app.dependency_overrides.clear()
    assert resp.status_code == 204


@pytest.mark.integration
async def test_get_heartbeat_not_found(test_db: AsyncSession) -> None:
    import uuid
    async with await _client(test_db) as c:
        resp = await c.get(f"/api/v1/heartbeats/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.integration
async def test_update_heartbeat(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        create = await c.post("/api/v1/heartbeats/", json={"name": "Old", "expected_interval_seconds": 60})
        pid = create.json()["public_id"]
        resp = await c.patch(f"/api/v1/heartbeats/{pid}", json={"name": "New"})
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"
