from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from monitoring.models.maintenance import MaintenanceWindow, MaintenanceWindowMonitor
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.schemas.maintenance import MaintenanceWindowCreate, MaintenanceWindowUpdate

logger = structlog.get_logger(__name__)



def _as_aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize to UTC-aware for comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class MaintenanceService:
    """Business logic for maintenance windows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_window(
        self,
        data: MaintenanceWindowCreate,
        created_by: int | None = None,
    ) -> MaintenanceWindow:
        organization = (
            await self.db.execute(
                select(Organization).where(Organization.public_id == data.organization_id),
            )
        ).scalar_one_or_none()
        if organization is None:
            raise ValueError("Organization not found")

        window = MaintenanceWindow(
            organization_id=organization.id,
            title=data.title,
            description=data.description,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            notify_subscribers=data.notify_subscribers,
            created_by=created_by,
        )
        self.db.add(window)
        await self.db.flush()

        for monitor_public_id in data.monitor_ids:
            monitor = (
                await self.db.execute(
                    select(Monitor).where(Monitor.public_id == monitor_public_id),
                )
            ).scalar_one_or_none()
            if monitor is None or monitor.organization_id != organization.id:
                raise ValueError(f"Monitor {monitor_public_id} not found")
            self.db.add(
                MaintenanceWindowMonitor(
                    maintenance_window_id=window.id,
                    monitor_id=monitor.id,
                ),
            )

        await self.db.flush()
        return await self.get_window(window.public_id)

    async def get_window(self, window_public_id: uuid.UUID) -> MaintenanceWindow | None:
        result = await self.db.execute(
            select(MaintenanceWindow)
            .options(
                selectinload(MaintenanceWindow.monitors).selectinload(
                    MaintenanceWindowMonitor.monitor,
                ),
            )
            .execution_options(populate_existing=True)
            .where(MaintenanceWindow.public_id == window_public_id),
        )
        return result.scalar_one_or_none()

    async def list_windows(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[MaintenanceWindow], int]:
        base_stmt = select(MaintenanceWindow).where(
            MaintenanceWindow.organization_id == organization_id,
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.options(
                selectinload(MaintenanceWindow.monitors).selectinload(
                    MaintenanceWindowMonitor.monitor,
                ),
            )
            .order_by(MaintenanceWindow.starts_at.desc())
            .offset(skip)
            .limit(limit),
        )
        return list(result.scalars().all()), total

    async def update_window(
        self,
        window_public_id: uuid.UUID,
        data: MaintenanceWindowUpdate,
    ) -> MaintenanceWindow | None:
        window = await self.get_window(window_public_id)
        if window is None:
            return None

        values = data.model_dump(exclude_unset=True)
        monitor_ids = values.pop("monitor_ids", None)
        for key, value in values.items():
            setattr(window, key, value)

        if monitor_ids is not None:
            resolved_ids: list[int] = []
            for monitor_public_id in monitor_ids:
                monitor = (
                    await self.db.execute(
                        select(Monitor).where(Monitor.public_id == monitor_public_id),
                    )
                ).scalar_one_or_none()
                if monitor is None or monitor.organization_id != window.organization_id:
                    raise ValueError(f"Monitor {monitor_public_id} not found")
                resolved_ids.append(monitor.id)

            for association in list(window.monitors):
                await self.db.delete(association)
            await self.db.flush()
            for monitor_id in resolved_ids:
                self.db.add(
                    MaintenanceWindowMonitor(
                        maintenance_window_id=window.id,
                        monitor_id=monitor_id,
                    ),
                )

        await self.db.flush()
        return await self.get_window(window.public_id)

    async def delete_window(self, window_public_id: uuid.UUID) -> bool:
        window = await self.get_window(window_public_id)
        if window is None:
            return False
        await self.db.delete(window)
        return True

    async def get_active_windows(
        self,
        organization_id: int | None = None,
        now: datetime | None = None,
        include_upcoming: bool = False,
    ) -> list[MaintenanceWindow]:
        """Active (and optionally upcoming) maintenance windows."""
        now = now or datetime.now(UTC)
        stmt = select(MaintenanceWindow).options(
            selectinload(MaintenanceWindow.monitors).selectinload(
                MaintenanceWindowMonitor.monitor,
            ),
        )
        if organization_id is not None:
            stmt = stmt.where(MaintenanceWindow.organization_id == organization_id)
        if include_upcoming:
            stmt = stmt.where(MaintenanceWindow.ends_at > now)
        else:
            stmt = stmt.where(
                MaintenanceWindow.starts_at <= now,
                MaintenanceWindow.ends_at > now,
            )
        result = await self.db.execute(stmt.order_by(MaintenanceWindow.starts_at))
        return list(result.scalars().all())

    async def get_suppressed_monitor_ids(self, now: datetime | None = None) -> set[int]:
        """Internal monitor IDs currently inside an active maintenance window."""
        now = now or datetime.now(UTC)
        suppressed: set[int] = set()
        for window in await self.get_active_windows(now=now):
            if window.monitors:
                suppressed.update(association.monitor_id for association in window.monitors)
            else:
                # Org-wide window: every enabled monitor in the organization.
                result = await self.db.execute(
                    select(Monitor.id).where(
                        Monitor.organization_id == window.organization_id,
                        Monitor.enabled == True,  # noqa: E712
                    ),
                )
                suppressed.update(result.scalars().all())
        return suppressed

    def _window_status(self, window: MaintenanceWindow, now: datetime) -> str:
        starts_at = _as_aware(window.starts_at)
        ends_at = _as_aware(window.ends_at)
        if starts_at > now:
            return "SCHEDULED"
        if starts_at <= now < ends_at:
            return "IN_PROGRESS"
        return "COMPLETED"

    async def public_maintenance_payload(
        self,
        organization_id: int,
    ) -> list[dict[str, object]]:
        """Maintenance windows shown on public status pages (active + upcoming)."""
        now = datetime.now(UTC)
        windows = await self.get_active_windows(
            organization_id=organization_id,
            now=now,
            include_upcoming=True,
        )
        payload: list[dict[str, object]] = []
        for window in windows:
            monitor_ids = [association.monitor_id for association in window.monitors]
            payload.append(
                {
                    "id": window.public_id,
                    "title": window.title,
                    "description": window.description,
                    "starts_at": window.starts_at,
                    "ends_at": window.ends_at,
                    "status": self._window_status(window, now),
                    "notify_subscribers": window.notify_subscribers,
                    "monitor_ids": monitor_ids,
                },
            )
        return payload
