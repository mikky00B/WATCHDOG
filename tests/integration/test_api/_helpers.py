"""Shared helpers for API integration tests (register/login/org bootstrap)."""
from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from monitoring.database import get_db
from monitoring.main import app
from monitoring.models.organization import Organization
from monitoring.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def make_client(test_db: AsyncSession) -> AsyncClient:
    """Build an ASGI client bound to the in-memory test database."""

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def release_client() -> None:
    app.dependency_overrides.clear()


async def register_and_login(
    client: AsyncClient,
    test_db: AsyncSession,
    email: str = "owner@example.com",
) -> dict:
    """Register a user, verify the e-mail directly in the DB, and log in."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Owner User",
            "email": email,
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201, response.text
    result = await test_db.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.is_verified = True
    await test_db.flush()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200, login.text
    return login.json()


async def create_organization(
    client: AsyncClient,
    headers: dict[str, str],
    name: str = "Watchdog Org",
) -> dict:
    """Create an organization via the API and return its payload."""
    slug = f"org-{uuid.uuid4().hex[:10]}"
    response = await client.post(
        "/api/v1/organizations/",
        json={"name": name, "slug": slug},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def get_internal_org_id(test_db: AsyncSession, public_id: str) -> int:
    """Resolve the internal integer id of an organization from its public UUID."""
    result = await test_db.execute(
        select(Organization).where(Organization.public_id == uuid.UUID(public_id)),
    )
    return result.scalar_one().id
