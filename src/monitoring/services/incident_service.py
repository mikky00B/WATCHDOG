from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.incident import Incident, IncidentUpdate
from monitoring.models.monitor import Monitor
from monitoring.models.user import User
from monitoring.schemas.incident import IncidentCreate, IncidentUpdateCreate

OPEN_INCIDENT_STATUSES = {"OPEN", "ACKNOWLEDGED"}


class IncidentService:
    """Business logic for incident lifecycle management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_incident(self, data: IncidentCreate) -> Incident:
        existing = await self.get_open_incident_for_monitor(data.monitor_id)
        if existing is not None:
            return existing

        incident = Incident(**data.model_dump())
        self.db.add(incident)
        await self.db.flush()
        await self.db.refresh(incident)
        from monitoring.services.notification_service import AlertEventService

        await AlertEventService(self.db).queue_for_incident(
            incident,
            event_type="MONITOR_DOWN",
            message=incident.reason,
        )
        return incident

    async def create_or_update_for_failed_check(
        self,
        monitor: Monitor,
        reason: str | None,
        severity: str = "HIGH",
    ) -> Incident:
        incident = await self.get_open_incident_for_monitor(monitor.id)
        if incident is not None:
            if reason:
                incident.reason = reason
            await self.db.flush()
            await self.db.refresh(incident)
            return incident

        return await self.create_incident(
            IncidentCreate(
                monitor_id=monitor.id,
                organization_id=monitor.organization_id,
                title=f"{monitor.name} is {monitor.status}",
                severity=severity,
                reason=reason or "Monitor check failed",
                started_at=datetime.now(UTC),
            )
        )

    async def resolve_for_monitor(
        self,
        monitor: Monitor,
        note: str | None = None,
    ) -> Incident | None:
        incident = await self.get_open_incident_for_monitor(monitor.id)
        if incident is None:
            return None
        return await self.resolve_incident(incident.id, note=note)

    async def get_open_incident_for_monitor(self, monitor_id: int) -> Incident | None:
        stmt = (
            select(Incident)
            .where(
                Incident.monitor_id == monitor_id,
                Incident.status.in_(OPEN_INCIDENT_STATUSES),
            )
            .order_by(Incident.started_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_incident(self, incident_id: int) -> Incident | None:
        return await self.db.get(Incident, incident_id)

    async def list_incidents(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        organization_id: int | None = None,
        monitor_id: int | None = None,
    ) -> tuple[list[Incident], int]:
        base_stmt = select(Incident)
        if status is not None:
            base_stmt = base_stmt.where(Incident.status == status)
        if organization_id is not None:
            base_stmt = base_stmt.where(Incident.organization_id == organization_id)
        if monitor_id is not None:
            base_stmt = base_stmt.where(Incident.monitor_id == monitor_id)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(Incident.started_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def acknowledge_incident(
        self,
        incident_id: int,
        user: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        incident = await self.get_incident(incident_id)
        if incident is None:
            return None

        incident.status = "ACKNOWLEDGED"
        incident.acknowledged_at = datetime.now(UTC)
        incident.acknowledged_by = user.id if user is not None else None
        if note:
            await self.add_update(incident, note, user=user)
        await self.db.flush()
        await self.db.refresh(incident)
        return incident

    async def resolve_incident(
        self,
        incident_id: int,
        note: str | None = None,
        user: User | None = None,
    ) -> Incident | None:
        incident = await self.get_incident(incident_id)
        if incident is None:
            return None

        resolved_at = datetime.now(UTC)
        incident.status = "RESOLVED"
        incident.resolved_at = resolved_at
        started_at = incident.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        incident.duration_seconds = max(0, int((resolved_at - started_at).total_seconds()))
        if note:
            await self.add_update(incident, note, user=user)
        await self.db.flush()
        await self.db.refresh(incident)
        from monitoring.services.notification_service import AlertEventService

        await AlertEventService(self.db).queue_for_incident(
            incident,
            event_type="MONITOR_RECOVERED",
            message=note or "Monitor recovered",
        )
        return incident

    async def add_update(
        self,
        incident: Incident,
        message: str,
        visibility: str = "INTERNAL",
        user: User | None = None,
    ) -> IncidentUpdate:
        update = IncidentUpdate(
            incident_id=incident.id,
            user_id=user.id if user is not None else None,
            message=message,
            visibility=visibility,
        )
        self.db.add(update)
        await self.db.flush()
        await self.db.refresh(update)
        return update

    async def add_update_from_schema(
        self,
        incident_id: int,
        data: IncidentUpdateCreate,
        user: User | None = None,
    ) -> IncidentUpdate | None:
        incident = await self.get_incident(incident_id)
        if incident is None:
            return None
        return await self.add_update(
            incident,
            data.message,
            visibility=data.visibility,
            user=user,
        )
