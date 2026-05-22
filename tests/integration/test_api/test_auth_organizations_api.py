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


@pytest.mark.integration
async def test_register_login_and_me(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Owner User",
                "email": "owner@example.com",
                "password": "StrongPass123",
            },
        )
        blocked_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "StrongPass123"},
        )
        result = await test_db.execute(select(User).where(User.email == "owner@example.com"))
        user = result.scalar_one()
        user.is_verified = True
        await test_db.flush()
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "StrongPass123"},
        )
        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
    app.dependency_overrides.clear()

    registered = response.json()
    assert registered["message"] == "Verification code sent. Check your email before logging in."
    assert registered["user"]["email"] == "owner@example.com"
    assert registered["user"]["is_verified"] is False
    assert blocked_login.status_code == 403
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


@pytest.mark.integration
async def test_verify_email_allows_login(test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "monitoring.services.auth_service.AuthService._new_verification_code",
        staticmethod(lambda: "123456"),
    )
    async with await _make_client(test_db) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Verify User",
                "email": "verify@example.com",
                "password": "StrongPass123",
            },
        )
        bad_verify = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "verify@example.com", "code": "000000"},
        )
        verified = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "verify@example.com", "code": "123456"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "verify@example.com", "password": "StrongPass123"},
        )
    app.dependency_overrides.clear()

    assert registered.status_code == 201
    assert bad_verify.status_code == 400
    assert verified.status_code == 200
    assert verified.json()["is_verified"] is True
    assert login.status_code == 200
    assert login.json()["refresh_token"]


@pytest.mark.integration
async def test_refresh_logout_and_password_reset(
    test_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "monitoring.services.auth_service.AuthService._new_verification_code",
        staticmethod(lambda: "123456"),
    )
    async with await _make_client(test_db) as client:
        await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Reset User",
                "email": "reset@example.com",
                "password": "StrongPass123",
            },
        )
        await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "reset@example.com", "code": "123456"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": "StrongPass123"},
        )
        refresh_token = login.json()["refresh_token"]
        refreshed = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        logout = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        blocked_refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        forgot = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "reset@example.com"},
        )
        bad_reset = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "email": "reset@example.com",
                "code": "000000",
                "new_password": "NewStrongPass123",
            },
        )
        reset = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "email": "reset@example.com",
                "code": "123456",
                "new_password": "NewStrongPass123",
            },
        )
        old_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": "StrongPass123"},
        )
        new_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": "NewStrongPass123"},
        )
    app.dependency_overrides.clear()

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert logout.status_code == 200
    assert blocked_refresh.status_code == 401
    assert forgot.status_code == 200
    assert bad_reset.status_code == 400
    assert reset.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.integration
async def test_create_and_list_organizations(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        registered = await _register(client, test_db)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        created = await client.post(
            "/api/v1/organizations/",
            json={"name": "CleverWeb Studio", "slug": "cleverweb-studio"},
            headers=headers,
        )
        listed = await client.get("/api/v1/organizations/", headers=headers)
    app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["slug"] == "cleverweb-studio"
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["organizations"][0]["slug"] == "cleverweb-studio"


@pytest.mark.integration
async def test_organization_scoped_monitor_requires_membership(
    test_db: AsyncSession,
) -> None:
    async with await _make_client(test_db) as client:
        owner = await _register(client, test_db, "owner@example.com")
        other = await _register(client, test_db, "other@example.com")
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}

        org = await client.post(
            "/api/v1/organizations/",
            json={"name": "Agency", "slug": "agency"},
            headers=owner_headers,
        )
        org_id = org.json()["public_id"]

        created = await client.post(
            "/api/v1/monitors/",
            json={
                "organization_id": org_id,
                "name": "Client API",
                "url": "https://api.example.com",
                "interval_seconds": 60,
            },
            headers=owner_headers,
        )
        owner_list = await client.get(
            f"/api/v1/monitors/?organization_id={org_id}",
            headers=owner_headers,
        )
        owner_stats = await client.get(
            f"/api/v1/stats?organization_id={org_id}",
            headers=owner_headers,
        )
        other_get = await client.get(
            f"/api/v1/monitors/{created.json()['public_id']}",
            headers=other_headers,
        )
        other_list = await client.get(
            f"/api/v1/monitors/?organization_id={org_id}",
            headers=other_headers,
        )
        anonymous_create = await client.post(
            "/api/v1/monitors/",
            json={
                "organization_id": org_id,
                "name": "Blocked",
                "url": "https://blocked.example.com",
                "interval_seconds": 60,
            },
        )
    app.dependency_overrides.clear()

    assert created.status_code == 201
    assert owner_list.status_code == 200
    assert owner_list.json()["total"] == 1
    assert owner_stats.status_code == 200
    assert owner_stats.json()["total_monitors"] == 1
    assert other_get.status_code == 404
    assert other_list.status_code == 404
    assert anonymous_create.status_code == 404


@pytest.mark.integration
async def test_create_and_ping_heartbeat_monitor(test_db: AsyncSession) -> None:
    async with await _make_client(test_db) as client:
        registered = await _register(client, test_db)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        org = await client.post(
            "/api/v1/organizations/",
            json={"name": "Heartbeat Org", "slug": "heartbeat-org"},
            headers=headers,
        )
        created = await client.post(
            "/api/v1/monitors/",
            json={
                "organization_id": org.json()["public_id"],
                "name": "Daily Backup",
                "monitor_type": "HEARTBEAT",
                "interval_seconds": 300,
            },
            headers=headers,
        )
        heartbeat_url = created.json()["heartbeat_url"]
        ping = await client.post(heartbeat_url)
    app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["url"] is None
    assert created.json()["monitor_type"] == "HEARTBEAT"
    assert created.json()["heartbeat_key"].startswith("hb_")
    assert heartbeat_url.startswith("/api/v1/monitors/heartbeat/hb_")
    assert ping.status_code == 200
    assert ping.json()["last_checked_at"] is not None
