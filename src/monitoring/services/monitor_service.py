from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.monitor import Monitor
from monitoring.schemas.monitor import MonitorCreate, MonitorUpdate


class MonitorService:
    """Business logic for monitor management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_monitor(self, data: MonitorCreate) -> Monitor:
        """
        Create a new monitor.

        Args:
            data: Monitor creation data

        Returns:
            Created monitor
        """
        # Serialize Pydantic model, converting HttpUrl to string
        monitor_data = data.model_dump()
        monitor_data["url"] = str(monitor_data["url"])
        monitor = Monitor(**monitor_data)
        self.db.add(monitor)
        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def get_monitor(self, monitor_id: uuid.UUID) -> Monitor | None:
        """
        Get monitor by public ID.

        Args:
            monitor_id: Monitor public UUID

        Returns:
            Monitor if found, None otherwise
        """
        stmt = select(Monitor).where(Monitor.public_id == monitor_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_monitor_by_internal_id(self, monitor_id: int) -> Monitor | None:
        """
        Get monitor by internal ID.

        Args:
            monitor_id: Monitor internal ID

        Returns:
            Monitor if found, None otherwise
        """
        return await self.db.get(Monitor, monitor_id)

    async def list_monitors(
        self,
        skip: int = 0,
        limit: int = 100,
        enabled_only: bool = False,
    ) -> tuple[list[Monitor], int]:
        """
        List monitors with pagination and total count.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            enabled_only: Filter for enabled monitors only

        Returns:
            A tuple containing the list of monitors and the total count
        """
        # Base query for monitors
        base_stmt = select(Monitor)
        if enabled_only:
            base_stmt = base_stmt.where(Monitor.enabled == True)  # noqa: E712

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = base_stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        monitors = list(result.scalars().all())

        return monitors, total

    async def update_monitor(
        self,
        monitor_id: uuid.UUID,
        data: MonitorUpdate,
    ) -> Monitor | None:
        """
        Update monitor.

        Args:
            monitor_id: Monitor public UUID
            data: Update data

        Returns:
            Updated monitor if found, None otherwise
        """
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            # Serialize HttpUrl to string if needed
            setattr(monitor, key, str(value) if key == "url" else value)

        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def delete_monitor(self, monitor_id: uuid.UUID) -> bool:
        """
        Delete monitor.

        Args:
            monitor_id: Monitor public UUID

        Returns:
            True if deleted, False if not found
        """
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return False

        await self.db.delete(monitor)
        return True
