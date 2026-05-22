from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.heartbeat import Heartbeat
from monitoring.models.organization import Organization
from monitoring.schemas.heartbeat import HeartbeatCreate, HeartbeatUpdate

logger = structlog.get_logger(__name__)


class HeartbeatService:
    """Business logic for heartbeat management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_heartbeat(self, data: HeartbeatCreate) -> Heartbeat:
        """
        Create a new heartbeat.

        Args:
            data: Heartbeat creation data

        Returns:
            Created heartbeat
        """
        heartbeat_data = data.model_dump()
        organization_public_id = heartbeat_data.pop("organization_id", None)
        if organization_public_id is not None:
            organization = await self.get_organization_by_public_id(
                organization_public_id,
            )
            if organization is None:
                raise ValueError("Organization not found")
            heartbeat_data["organization_id"] = organization.id
        heartbeat = Heartbeat(**heartbeat_data)
        self.db.add(heartbeat)
        await self.db.flush()
        await self.db.refresh(heartbeat)

        logger.info(
            "heartbeat_created",
            heartbeat_id=heartbeat.id,
            name=heartbeat.name,
            public_id=str(heartbeat.public_id),
        )

        return heartbeat

    async def get_organization_by_public_id(
        self,
        organization_id: uuid.UUID,
    ) -> Organization | None:
        stmt = select(Organization).where(Organization.public_id == organization_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_heartbeat(self, heartbeat_id: uuid.UUID) -> Heartbeat | None:
        """
        Get heartbeat by public ID.

        Args:
            heartbeat_id: Heartbeat public UUID

        Returns:
            Heartbeat if found, None otherwise
        """
        stmt = select(Heartbeat).where(Heartbeat.public_id == heartbeat_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_heartbeats(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: int | None = None,
    ) -> tuple[list[Heartbeat], int]:
        """
        List heartbeats with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            A tuple containing the list of heartbeats and the total count
        """
        base_stmt = select(Heartbeat)
        if organization_id is not None:
            base_stmt = base_stmt.where(Heartbeat.organization_id == organization_id)

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = base_stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        heartbeats = list(result.scalars().all())

        return heartbeats, total

    async def update_heartbeat(
        self,
        heartbeat_id: uuid.UUID,
        data: HeartbeatUpdate,
    ) -> Heartbeat | None:
        """
        Update heartbeat.

        Args:
            heartbeat_id: Heartbeat public UUID
            data: Update data

        Returns:
            Updated heartbeat if found, None otherwise
        """
        heartbeat = await self.get_heartbeat(heartbeat_id)
        if heartbeat is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(heartbeat, key, value)

        await self.db.flush()
        await self.db.refresh(heartbeat)

        logger.info(
            "heartbeat_updated",
            heartbeat_id=heartbeat.id,
            name=heartbeat.name,
        )

        return heartbeat

    async def delete_heartbeat(self, heartbeat_id: uuid.UUID) -> bool:
        """
        Delete heartbeat.

        Args:
            heartbeat_id: Heartbeat public UUID

        Returns:
            True if deleted, False if not found
        """
        heartbeat = await self.get_heartbeat(heartbeat_id)
        if heartbeat is None:
            return False

        await self.db.delete(heartbeat)

        logger.info(
            "heartbeat_deleted",
            heartbeat_id=heartbeat.id,
            name=heartbeat.name,
        )

        return True

    async def ping_heartbeat(self, heartbeat_id: uuid.UUID) -> Heartbeat | None:
        """
        Record a heartbeat ping.

        Args:
            heartbeat_id: Heartbeat public UUID

        Returns:
            Updated heartbeat if found, None otherwise
        """
        heartbeat = await self.get_heartbeat(heartbeat_id)
        if heartbeat is None:
            return None

        heartbeat.last_heartbeat_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(heartbeat)

        logger.info(
            "heartbeat_ping",
            heartbeat_id=heartbeat.id,
            name=heartbeat.name,
            timestamp=heartbeat.last_heartbeat_at,
        )

        return heartbeat
