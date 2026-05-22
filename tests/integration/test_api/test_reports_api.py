from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.check_result import CheckResult
from monitoring.models.incident import Incident
from monitoring.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_client(test_db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, test_db: AsyncSession) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Report Owner",
            "email": "reports@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    result = await test_db.execute(select(User).where(User.email == "reports@example.com"))
    user = result.scalar_one()
    user.is_verified = True
    await test_db.flush()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reports@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200
    return login.json()


@pytest.mark.integration
async def test_monthly_report_returns_server_calculated_metrics(
    test_db: AsyncSession,
) -> None:
    async with await _make_client(test_db) as client:
        registered = await _register(client, test_db)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}

        org = await client.post(
            "/api/v1/organizations/",
            json={"name": "Report Studio", "slug": "report-studio"},
            headers=headers,
        )
        org_body = org.json()
        created_client = await client.post(
            f"/api/v1/organizations/{org_body['public_id']}/clients",
            json={"name": "Acme Reports"},
            headers=headers,
        )
        monitor = await client.post(
            "/api/v1/monitors/",
            json={
                "organization_id": org_body["public_id"],
                "client_id": created_client.json()["public_id"],
                "name": "Acme API",
                "url": "https://api.acme.example.com/health",
                "interval_seconds": 60,
            },
            headers=headers,
        )
        monitor_body = monitor.json()
        checks = [
            CheckResult(
                monitor_id=monitor_body["id"],
                organization_id=org_body["id"],
                status_code=200,
                latency_ms=100,
                success=True,
                checked_at=datetime(2026, 5, 4, 10, 0),
            ),
            CheckResult(
                monitor_id=monitor_body["id"],
                organization_id=org_body["id"],
                status_code=200,
                latency_ms=200,
                success=True,
                checked_at=datetime(2026, 5, 4, 10, 5),
            ),
            CheckResult(
                monitor_id=monitor_body["id"],
                organization_id=org_body["id"],
                status_code=500,
                latency_ms=None,
                success=False,
                checked_at=datetime(2026, 5, 4, 10, 10),
            ),
        ]
        test_db.add_all(checks)
        test_db.add(
            Incident(
                organization_id=org_body["id"],
                monitor_id=monitor_body["id"],
                title="Acme API outage",
                status="RESOLVED",
                severity="HIGH",
                reason="HTTP 500",
                started_at=datetime(2026, 5, 4, 10, 10),
                resolved_at=datetime(2026, 5, 4, 10, 40),
                duration_seconds=1800,
            ),
        )
        await test_db.flush()

        report = await client.get(
            "/api/v1/reports/monthly",
            params={
                "organization_id": org_body["public_id"],
                "client_id": created_client.json()["public_id"],
                "year": 2026,
                "month": 5,
            },
            headers=headers,
        )
        html_report = await client.get(
            "/api/v1/reports/monthly/html",
            params={
                "organization_id": org_body["public_id"],
                "client_id": created_client.json()["public_id"],
                "year": 2026,
                "month": 5,
            },
            headers=headers,
        )
    app.dependency_overrides.clear()

    assert report.status_code == 200
    body = report.json()
    assert body["client_name"] == "Acme Reports"
    assert body["monitors_included"] == 1
    assert body["uptime_percentage"] == 66.67
    assert body["total_downtime_seconds"] == 1800
    assert body["incident_count"] == 1
    assert body["average_response_time_ms"] == 150
    assert body["monitors"][0]["failed_checks"] == 1
    assert body["incidents"][0]["title"] == "Acme API outage"
    assert html_report.status_code == 200
    assert "Acme Reports Reliability Report" in html_report.text
