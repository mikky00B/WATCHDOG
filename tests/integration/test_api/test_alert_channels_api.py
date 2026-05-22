from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _client(test_db: AsyncSession) -> AsyncClient:
    async def _override():
        yield test_db

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register_and_org(client: AsyncClient, test_db: AsyncSession) -> tuple[dict[str, str], int]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Owner User",
            "email": "owner@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    result = await test_db.execute(select(User).where(User.email == "owner@example.com"))
    user = result.scalar_one()
    user.is_verified = True
    await test_db.flush()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "StrongPass123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org = await client.post(
        "/api/v1/organizations/",
        json={"name": "Agency", "slug": "agency"},
        headers=headers,
    )
    return headers, org.json()["id"]


@pytest.mark.integration
async def test_create_list_and_test_alert_channel(test_db: AsyncSession) -> None:
    async with await _client(test_db) as client:
        headers, organization_id = await _register_and_org(client, test_db)
        created = await client.post(
            "/api/v1/alert-channels/",
            json={
                "organization_id": organization_id,
                "name": "Main Email",
                "channel_type": "EMAIL",
                "config": {"email": "alerts@example.com"},
            },
            headers=headers,
        )
        listed = await client.get(
            f"/api/v1/alert-channels/?organization_id={organization_id}",
            headers=headers,
        )
        test_event = await client.post(
            f"/api/v1/alert-channels/{created.json()['id']}/test",
            headers=headers,
        )
    app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["channel_type"] == "EMAIL"
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert test_event.status_code == 200
    assert test_event.json()["event_type"] == "TEST"
    assert test_event.json()["status"] == "PENDING"
