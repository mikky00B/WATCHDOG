from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.models.client import Client
from monitoring.models.incident import Incident
from monitoring.schemas.infrastructure import InfraSummary
from monitoring.services.analytics_service import AnalyticsService
from monitoring.services.infrastructure_service import InfrastructureService
from monitoring.services.monitor_service import MonitorService
from monitoring.services.organization_service import OrganizationService
from monitoring.utils.time_period import InvalidPeriodError, parse_period

router = APIRouter()


async def _resolve_org(
    organization_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> int:
    organization = await OrganizationService(db).get_organization(organization_id)
    if (
        organization is None
        or current_user is None
        or not await OrganizationService(db).user_can_access(current_user, organization.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization.id


def _hours(period: str) -> float:
    try:
        return parse_period(period)
    except InvalidPeriodError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


async def _resolve_monitor(
    monitor_id: uuid.UUID,
    internal_org_id: int,
    db: DbSession,
) -> int | None:
    monitor = await MonitorService(db).get_monitor(monitor_id)
    if monitor is None or monitor.organization_id != internal_org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor.id


@router.get("/response-times")
async def response_time_series(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    period: str = Query(default="24h"),
    monitor_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
) -> dict:
    """Historical response time buckets (avg, p95) for charts."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    internal_monitor_id = (
        await _resolve_monitor(monitor_id, internal_org_id, db) if monitor_id else None
    )
    internal_client_id = None
    if client_id is not None:
        client = (
            await db.execute(select(Client).where(Client.public_id == client_id))
        ).scalar_one_or_none()
        if client is None or client.organization_id != internal_org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        internal_client_id = client.id
    series = await AnalyticsService(db).response_time_series(
        internal_org_id,
        hours=_hours(period),
        monitor_id=internal_monitor_id,
        client_id=internal_client_id,
    )
    return {"series": series}


@router.get("/uptime")
async def uptime_series(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    period: str = Query(default="7d"),
    monitor_id: uuid.UUID | None = None,
) -> dict:
    """Historical uptime percentage buckets for charts."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    internal_monitor_id = (
        await _resolve_monitor(monitor_id, internal_org_id, db) if monitor_id else None
    )
    series = await AnalyticsService(db).uptime_series(
        internal_org_id,
        hours=_hours(period),
        monitor_id=internal_monitor_id,
    )
    return {"series": series}


@router.get("/service-health")
async def service_health(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
) -> dict:
    """Service health overview: per-monitor status, uptime, latency, maintenance."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    return await AnalyticsService(db).service_health(internal_org_id)


@router.get("/infrastructure")
async def infrastructure_overview(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    history_hours: float = Query(default=6.0, gt=0, le=720),
) -> InfraSummary:
    """Host health overview for dashboards."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    hosts = await InfrastructureService(db).list_hosts(
        internal_org_id,
        history_hours=history_hours,
    )
    return InfraSummary(hosts=hosts, total_hosts=len(hosts))


@router.get("/incidents/{incident_id}/timeline")
async def incident_timeline(
    incident_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> dict:
    """Correlated incident timeline (updates, alerts, failed checks, log errors)."""
    incident = (
        await db.execute(select(Incident).where(Incident.id == incident_id))
    ).scalar_one_or_none()
    if incident is None or (
        incident.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                incident.organization_id,
            )
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return await AnalyticsService(db).incident_timeline(incident)
