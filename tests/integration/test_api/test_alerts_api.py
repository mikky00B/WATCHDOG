"""Integration tests for /api/v1/alerts endpoints."""
from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.main import app
from monitoring.database import get_db
from monitoring.models.alert import Alert
from monitoring.models.monitor import Monitor


async def _client(test_db: AsyncSession) -> AsyncClient:
    async def _override():
        yield test_db
    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_monitor_and_alert(test_db: AsyncSession) -> tuple[Monitor, Alert]:
    m = Monitor(name="Test", url="https://x.com", interval_seconds=60)
    test_db.add(m)
    await test_db.flush()
    a = Alert(
        monitor_id=m.id, severity="warning",
        title="Down", message="No response",
        triggered_at=datetime.utcnow(),
    )
    test_db.add(a)
    await test_db.commit()
    await test_db.refresh(a)
    return m, a


@pytest.mark.integration
async def test_list_alerts_empty(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        resp = await c.get("/api/v1/alerts/")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
async def test_list_alerts_returns_items(test_db: AsyncSession) -> None:
    _, _ = await _seed_monitor_and_alert(test_db)
    async with await _client(test_db) as c:
        resp = await c.get("/api/v1/alerts/")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.integration
async def test_get_alert(test_db: AsyncSession) -> None:
    _, alert = await _seed_monitor_and_alert(test_db)
    async with await _client(test_db) as c:
        resp = await c.get(f"/api/v1/alerts/{alert.id}")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["id"] == alert.id


@pytest.mark.integration
async def test_get_alert_not_found(test_db: AsyncSession) -> None:
    async with await _client(test_db) as c:
        resp = await c.get("/api/v1/alerts/99999")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.integration
async def test_resolve_alert(test_db: AsyncSession) -> None:
    _, alert = await _seed_monitor_and_alert(test_db)
    async with await _client(test_db) as c:
        resp = await c.post(f"/api/v1/alerts/{alert.id}/resolve")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
    assert resp.json()["resolved_at"] is not None


@pytest.mark.integration
async def test_acknowledge_alert(test_db: AsyncSession) -> None:
    _, alert = await _seed_monitor_and_alert(test_db)
    async with await _client(test_db) as c:
        resp = await c.post(f"/api/v1/alerts/{alert.id}/acknowledge")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] is True


@pytest.mark.integration
async def test_list_unresolved_only(test_db: AsyncSession) -> None:
    _, alert = await _seed_monitor_and_alert(test_db)
    async with await _client(test_db) as c:
        # Resolve it
        await c.post(f"/api/v1/alerts/{alert.id}/resolve")
        # List unresolved — should be empty
        resp = await c.get("/api/v1/alerts/?unresolved_only=true")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []
