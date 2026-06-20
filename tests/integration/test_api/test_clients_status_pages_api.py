from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_client(test_db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, test_db: AsyncSession, email: str = "owner@example.com") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Owner User",
            "email": email,
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    result = await test_db.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.is_verified = True
    await test_db.flush()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    return login.json()


async def _create_org(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/organizations/",
        json={"name": "Status Studio", "slug": "status-studio"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["public_id"]


@pytest.mark.integration
async def test_create_list_update_delete_client(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        registered = await _register(client, test_db)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        org_id = await _create_org(client, headers)

        created = await client.post(
            f"/api/v1/organizations/{org_id}/clients",
            json={
                "name": "Acme Stores",
                "contact_email": "ops@example.com",
                "notes": "Ecommerce client",
            },
            headers=headers,
        )
        client_id = created.json()["public_id"]
        listed = await client.get(
            f"/api/v1/organizations/{org_id}/clients",
            headers=headers,
        )
        updated = await client.patch(
            f"/api/v1/organizations/{org_id}/clients/{client_id}",
            json={"name": "Acme Commerce"},
            headers=headers,
        )
        deleted = await client.delete(
            f"/api/v1/organizations/{org_id}/clients/{client_id}",
            headers=headers,
        )
    app.dependency_overrides.clear()

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert updated.status_code == 200
    assert updated.json()["name"] == "Acme Commerce"
    assert deleted.status_code == 204


@pytest.mark.integration
async def test_client_scoped_monitor_and_public_status_page(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        registered = await _register(client, test_db)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        org_id = await _create_org(client, headers)

        created_client = await client.post(
            f"/api/v1/organizations/{org_id}/clients",
            json={"name": "Acme Stores"},
            headers=headers,
        )
        client_id = created_client.json()["public_id"]
        monitor = await client.post(
            "/api/v1/monitors/",
            json={
                "organization_id": org_id,
                "client_id": client_id,
                "name": "Acme Website",
                "url": "https://acme.example.com",
                "interval_seconds": 60,
            },
            headers=headers,
        )
        monitors = await client.get(
            f"/api/v1/monitors/?organization_id={org_id}&client_id={client_id}",
            headers=headers,
        )
        page = await client.post(
            "/api/v1/status-pages/",
            json={
                "organization_id": org_id,
                "name": "Acme Status",
                "slug": "acme-status",
                "brand_color": "#2563eb",
            },
            headers=headers,
        )
        service = await client.post(
            f"/api/v1/status-pages/{page.json()['public_id']}/services",
            json={
                "monitor_id": monitor.json()["public_id"],
                "display_name": "Website",
                "sort_order": 0,
            },
            headers=headers,
        )
        services = await client.get(
            f"/api/v1/status-pages/{page.json()['public_id']}/services",
            headers=headers,
        )
        public = await client.get("/api/v1/public/status-pages/acme-status")
        deleted_service = await client.delete(
            f"/api/v1/status-pages/{page.json()['public_id']}/services/{service.json()['public_id']}",
            headers=headers,
        )
        services_after_delete = await client.get(
            f"/api/v1/status-pages/{page.json()['public_id']}/services",
            headers=headers,
        )
    app.dependency_overrides.clear()

    assert created_client.status_code == 201
    assert monitor.status_code == 201
    assert monitor.json()["client_id"] == created_client.json()["id"]
    assert monitors.status_code == 200
    assert monitors.json()["total"] == 1
    assert page.status_code == 201
    assert service.status_code == 201
    assert services.status_code == 200
    assert services.json()["total"] == 1
    assert public.status_code == 200
    assert public.json()["name"] == "Acme Status"
    assert public.json()["overall_status"] == "OPERATIONAL"
    assert public.json()["services"][0]["display_name"] == "Website"
    assert deleted_service.status_code == 204
    assert services_after_delete.status_code == 200
    assert services_after_delete.json()["total"] == 0
