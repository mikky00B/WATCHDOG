from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.check_result import CheckResult
from monitoring.models.client import Client
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.schemas.monitor import MonitorCreate, MonitorUpdate
from monitoring.services.checker_service import CheckerService
from monitoring.services.incident_service import IncidentService


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
        if monitor_data["url"] is not None:
            monitor_data["url"] = str(monitor_data["url"])
        organization_public_id = monitor_data.pop("organization_id", None)
        client_public_id = monitor_data.pop("client_id", None)
        if organization_public_id is not None:
            organization = await self.get_organization_by_public_id(
                organization_public_id,
            )
            if organization is None:
                raise ValueError("Organization not found")
            monitor_data["organization_id"] = organization.id
            if client_public_id is not None:
                client = await self.get_client_by_public_id(client_public_id)
                if client is None or client.organization_id != organization.id:
                    raise ValueError("Client not found")
                monitor_data["client_id"] = client.id
        if monitor_data["monitor_type"] == "HEARTBEAT":
            monitor_data["heartbeat_key"] = f"hb_{secrets.token_urlsafe(12)}"
            monitor_data["status"] = "UNKNOWN"
            monitor_data["next_check_at"] = datetime.now(UTC) + timedelta(
                seconds=monitor_data["interval_seconds"],
            )
        monitor = Monitor(**monitor_data)
        self.db.add(monitor)
        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def get_organization_by_public_id(
        self,
        organization_id: uuid.UUID,
    ) -> Organization | None:
        stmt = select(Organization).where(Organization.public_id == organization_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_client_by_public_id(self, client_id: uuid.UUID) -> Client | None:
        stmt = select(Client).where(Client.public_id == client_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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

    async def get_monitor_by_heartbeat_key(self, heartbeat_key: str) -> Monitor | None:
        stmt = select(Monitor).where(Monitor.heartbeat_key == heartbeat_key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def ping_heartbeat_monitor(self, heartbeat_key: str) -> Monitor | None:
        monitor = await self.get_monitor_by_heartbeat_key(heartbeat_key)
        if monitor is None or monitor.monitor_type != "HEARTBEAT":
            return None

        now = datetime.now(UTC)
        monitor.last_checked_at = now
        monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
        monitor.status = "UP"
        monitor.consecutive_successes += 1
        monitor.consecutive_failures = 0
        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def list_monitors(
        self,
        skip: int = 0,
        limit: int = 100,
        enabled_only: bool = False,
        organization_id: int | None = None,
        client_id: int | None = None,
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
        if organization_id is not None:
            base_stmt = base_stmt.where(Monitor.organization_id == organization_id)
        if client_id is not None:
            base_stmt = base_stmt.where(Monitor.client_id == client_id)

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
            if key == "url" and value is not None:
                value = str(value)
            if key in {"monitor_type", "http_method"} and isinstance(value, str):
                value = value.upper()
            setattr(monitor, key, value)

        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def pause_monitor(self, monitor_id: uuid.UUID) -> Monitor | None:
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        monitor.enabled = False
        monitor.status = "PAUSED"
        monitor.next_check_at = None
        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def resume_monitor(self, monitor_id: uuid.UUID) -> Monitor | None:
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        monitor.enabled = True
        if monitor.monitor_type == "HEARTBEAT":
            monitor.next_check_at = datetime.now(UTC) + timedelta(seconds=monitor.interval_seconds)
        else:
            monitor.next_check_at = datetime.now(UTC)
        if monitor.status == "PAUSED":
            monitor.status = "UNKNOWN"
        await self.db.flush()
        await self.db.refresh(monitor)
        return monitor

    async def run_check_now(self, monitor_id: uuid.UUID) -> CheckResult | None:
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        now = datetime.now(UTC)
        if monitor.monitor_type == "HEARTBEAT":
            next_check_at = monitor.next_check_at
            if next_check_at is not None and next_check_at.tzinfo is None:
                next_check_at = next_check_at.replace(tzinfo=UTC)
            check_result = CheckResult(
                monitor_id=monitor.id,
                organization_id=monitor.organization_id,
                status_code=None,
                latency_ms=None,
                success=next_check_at is None or next_check_at >= now,
                error_message=None
                if next_check_at is None or next_check_at >= now
                else "Heartbeat missed",
                checked_at=now,
            )
        else:
            check_result = await CheckerService().check_http_endpoint(monitor)
            check_result.organization_id = monitor.organization_id

        self.db.add(check_result)
        monitor.last_checked_at = now
        monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
        if check_result.success:
            monitor.status = "UP"
            monitor.consecutive_successes += 1
            monitor.consecutive_failures = 0
            await IncidentService(self.db).resolve_for_monitor(
                monitor,
                note="Monitor recovered after manual check",
            )
        else:
            monitor.status = "DOWN"
            monitor.consecutive_failures += 1
            monitor.consecutive_successes = 0
            await IncidentService(self.db).create_or_update_for_failed_check(
                monitor,
                check_result.error_message or "Manual monitor check failed",
            )

        await self.db.flush()
        await self.db.refresh(check_result)
        await self.db.refresh(monitor)
        return check_result

    async def list_check_results(
        self,
        monitor_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[CheckResult], int] | None:
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        base_stmt = select(CheckResult).where(CheckResult.monitor_id == monitor.id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(CheckResult.checked_at.desc()).offset(skip).limit(limit),
        )
        return list(result.scalars().all()), total

    async def get_stats(self, monitor_id: uuid.UUID) -> dict[str, object] | None:
        monitor = await self.get_monitor(monitor_id)
        if monitor is None:
            return None

        base_stmt = select(CheckResult).where(CheckResult.monitor_id == monitor.id)
        total_checks = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        successful_checks = (
            await self.db.execute(
                select(func.count()).select_from(
                    base_stmt.where(CheckResult.success.is_(True)).subquery(),
                ),
            )
        ).scalar() or 0
        failed_checks = total_checks - successful_checks
        average_latency_ms = (
            await self.db.execute(
                select(func.avg(CheckResult.latency_ms)).where(
                    CheckResult.monitor_id == monitor.id,
                    CheckResult.latency_ms.is_not(None),
                ),
            )
        ).scalar()
        latest = (
            await self.db.execute(
                base_stmt.order_by(CheckResult.checked_at.desc()).limit(1),
            )
        ).scalar_one_or_none()

        return {
            "monitor_id": monitor.id,
            "total_checks": total_checks,
            "successful_checks": successful_checks,
            "failed_checks": failed_checks,
            "uptime_percentage": round((successful_checks / total_checks) * 100, 2)
            if total_checks
            else 0.0,
            "average_latency_ms": round(float(average_latency_ms), 2)
            if average_latency_ms is not None
            else None,
            "last_checked_at": latest.checked_at if latest is not None else None,
            "last_status_code": latest.status_code if latest is not None else None,
            "last_error_message": latest.error_message if latest is not None else None,
        }

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
