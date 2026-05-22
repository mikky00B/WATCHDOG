from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.organization import Organization, OrganizationMember
from monitoring.models.user import User
from monitoring.schemas.organization import OrganizationCreate


class OrganizationService:
    """Business logic for organizations and memberships."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_organization(self, data: OrganizationCreate, owner: User) -> Organization:
        existing = await self.get_organization_by_slug(data.slug)
        if existing is not None:
            raise ValueError("Organization slug is already in use")

        organization = Organization(name=data.name, slug=data.slug, owner_id=owner.id)
        self.db.add(organization)
        await self.db.flush()

        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=owner.id,
            role="OWNER",
            status="ACTIVE",
        )
        self.db.add(membership)
        await self.db.flush()
        await self.db.refresh(organization)
        return organization

    async def get_organization(self, organization_id: uuid.UUID) -> Organization | None:
        stmt = select(Organization).where(Organization.public_id == organization_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_organizations(
        self,
        user: User,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Organization], int]:
        base_stmt = (
            select(Organization)
            .join(OrganizationMember)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == "ACTIVE",
            )
        )
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        result = await self.db.execute(base_stmt.offset(skip).limit(limit))
        return list(result.scalars().all()), total

    async def user_can_access(self, user: User, organization_id: int) -> bool:
        stmt = select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "ACTIVE",
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

