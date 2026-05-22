"""Integration tests for /api/v1/monitors endpoints.

Uses FastAPI's async test client with the SQLite in-memory DB injected
via dependency override — no running server or PostgreSQL required.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.check_result import CheckResult
from monitoring.services.checker_service import CheckerService
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_client(test_db: AsyncSession) -> AsyncClient:
    """Return an HTTPX async test client with DB overridden."""
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client


@pytest.mark.integration
async def test_create_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        resp = await client.post("/api/v1/monitors/", json={
            "name": "My API",
            "url": "https://example.com/health",
            "interval_seconds": 60,
        })
    app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My API"
    assert "public_id" in data
    assert data["enabled"] is True


@pytest.mark.integration
async def test_create_monitor_invalid_url(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        resp = await client.post("/api/v1/monitors/", json={
            "name": "Bad Monitor",
            "url": "not-a-url",
            "interval_seconds": 60,
        })
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.integration
async def test_create_monitor_interval_too_low(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        resp = await client.post("/api/v1/monitors/", json={
            "name": "Bad", "url": "https://x.com", "interval_seconds": 5,
        })
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.integration
async def test_list_monitors_empty(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        resp = await client.get("/api/v1/monitors/")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"monitors": [], "total": 0}


@pytest.mark.integration
async def test_list_monitors_returns_created(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        await client.post("/api/v1/monitors/", json={
            "name": "A", "url": "https://a.com", "interval_seconds": 60,
        })
        resp = await client.get("/api/v1/monitors/")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert len(resp.json()["monitors"]) == 1


@pytest.mark.integration
async def test_get_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "API", "url": "https://api.com", "interval_seconds": 30,
        })
        pid = create.json()["public_id"]
        resp = await client.get(f"/api/v1/monitors/{pid}")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["public_id"] == pid


@pytest.mark.integration
async def test_get_monitor_not_found(test_db: AsyncSession) -> None:
    import uuid
    async with await _make_client(test_db) as client:
        resp = await client.get(f"/api/v1/monitors/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.integration
async def test_update_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "Old", "url": "https://old.com", "interval_seconds": 60,
        })
        pid = create.json()["public_id"]
        resp = await client.patch(f"/api/v1/monitors/{pid}", json={"name": "New"})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.integration
async def test_delete_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "Delete Me", "url": "https://del.com", "interval_seconds": 60,
        })
        pid = create.json()["public_id"]
        resp = await client.delete(f"/api/v1/monitors/{pid}")
    app.dependency_overrides.clear()
    assert resp.status_code == 204


@pytest.mark.integration
async def test_delete_monitor_not_found(test_db: AsyncSession) -> None:
    import uuid
    async with await _make_client(test_db) as client:
        resp = await client.delete(f"/api/v1/monitors/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.integration
async def test_pause_and_resume_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "Pausable", "url": "https://pause.com", "interval_seconds": 60,
        })
        pid = create.json()["public_id"]
        pause = await client.post(f"/api/v1/monitors/{pid}/pause")
        resume = await client.post(f"/api/v1/monitors/{pid}/resume")
    app.dependency_overrides.clear()

    assert pause.status_code == 200
    assert pause.json()["enabled"] is False
    assert pause.json()["status"] == "PAUSED"
    assert resume.status_code == 200
    assert resume.json()["enabled"] is True


@pytest.mark.integration
async def test_monitor_checks_and_stats(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "Stats", "url": "https://stats.com", "interval_seconds": 60,
        })
        body = create.json()
        check = CheckResult(
            monitor_id=body["id"],
            status_code=200,
            latency_ms=42.5,
            success=True,
            error_message=None,
        )
        test_db.add(check)
        await test_db.flush()

        checks = await client.get(f"/api/v1/monitors/{body['public_id']}/checks")
        stats = await client.get(f"/api/v1/monitors/{body['public_id']}/stats")
    app.dependency_overrides.clear()

    assert checks.status_code == 200
    assert checks.json()["total"] == 1
    assert checks.json()["results"][0]["success"] is True
    assert stats.status_code == 200
    assert stats.json()["total_checks"] == 1
    assert stats.json()["uptime_percentage"] == 100.0
    assert stats.json()["average_latency_ms"] == 42.5


@pytest.mark.integration
async def test_run_monitor_check(monkeypatch: pytest.MonkeyPatch, test_db: AsyncSession) -> None:
    async def fake_check(self: CheckerService, monitor):
        return CheckResult(
            monitor_id=monitor.id,
            status_code=200,
            latency_ms=55.0,
            success=True,
            error_message=None,
        )

    monkeypatch.setattr(CheckerService, "check_http_endpoint", fake_check)

    async with await _make_client(test_db) as client:
        create = await client.post("/api/v1/monitors/", json={
            "name": "Manual", "url": "https://manual.com", "interval_seconds": 60,
        })
        pid = create.json()["public_id"]
        result = await client.post(f"/api/v1/monitors/{pid}/run-check")
        monitor = await client.get(f"/api/v1/monitors/{pid}")
    app.dependency_overrides.clear()

    assert result.status_code == 200
    assert result.json()["success"] is True
    assert result.json()["status_code"] == 200
    assert monitor.json()["status"] == "UP"


@pytest.mark.integration
async def test_health_endpoint(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        resp = await client.get("/health")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
