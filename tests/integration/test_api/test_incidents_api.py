from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.incident import Incident
from monitoring.models.monitor import Monitor
from sqlalchemy.ext.asyncio import AsyncSession


async def _client(test_db: AsyncSession) -> AsyncClient:
    async def _override():
        yield test_db

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_incident(test_db: AsyncSession) -> Incident:
    monitor = Monitor(name="API", url="https://api.example.com", interval_seconds=60)
    test_db.add(monitor)
    await test_db.flush()
    incident = Incident(
        monitor_id=monitor.id,
        title="API is DOWN",
        reason="HTTP 500",
        started_at=datetime.now(UTC),
    )
    test_db.add(incident)
    await test_db.commit()
    await test_db.refresh(incident)
    return incident


@pytest.mark.integration
async def test_list_incidents_empty(test_db: AsyncSession) -> None:
    async with await _client(test_db) as client:
        response = await client.get("/api/v1/incidents/")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"incidents": [], "total": 0}


@pytest.mark.integration
async def test_get_acknowledge_resolve_incident(test_db: AsyncSession) -> None:
    incident = await _seed_incident(test_db)
    async with await _client(test_db) as client:
        fetched = await client.get(f"/api/v1/incidents/{incident.id}")
        acknowledged = await client.post(f"/api/v1/incidents/{incident.id}/acknowledge")
        resolved = await client.post(f"/api/v1/incidents/{incident.id}/resolve")
    app.dependency_overrides.clear()

    assert fetched.status_code == 200
    assert fetched.json()["id"] == incident.id
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["duration_seconds"] is not None

