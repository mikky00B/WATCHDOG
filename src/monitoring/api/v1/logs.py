from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from monitoring.dependencies import (
    CurrentUser,
    DbSession,
    OptionalCurrentUser,
    require_api_key_scope,
)
from monitoring.models.api_key import ApiKey
from monitoring.schemas.log import (
    MAX_LOG_BATCH,
    LogEntryResponse,
    LogIngestRequest,
    LogIngestResponse,
    LogList,
    LogStatsResponse,
)
from monitoring.services.log_service import LogService
from monitoring.services.monitor_service import MonitorService
from monitoring.services.organization_service import OrganizationService
from monitoring.utils.time_period import InvalidPeriodError, parse_period

router = APIRouter()
ingest_router = APIRouter()
_require_ingest_scope = require_api_key_scope("logs:write")


@ingest_router.post(
    "/ingest",
    response_model=LogIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_logs(
    payload: LogIngestRequest,
    db: DbSession,
    api_key: ApiKey = Depends(_require_ingest_scope),
) -> LogIngestResponse:
    """Ingest application logs. Machine clients authenticate with an API key."""
    if len(payload.logs) > MAX_LOG_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch exceeds {MAX_LOG_BATCH} log entries",
        )
    accepted, rejected = await LogService(db).ingest(
        api_key.organization_id,
        payload.logs,
        default_application=payload.application,
        default_environment=payload.environment,
    )
    await db.commit()
    return LogIngestResponse(accepted=accepted, rejected=rejected)


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


async def _resolve_client(
    client_id: uuid.UUID,
    internal_org_id: int,
    db: DbSession,
) -> int | None:
    client = await MonitorService(db).get_client_by_public_id(client_id)
    if client is None or client.organization_id != internal_org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found",
        )
    return client.id


@router.get("/", response_model=LogList)
async def search_logs(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    application: str | None = None,
    environment: str | None = None,
    level: str | None = None,
    client_id: uuid.UUID | None = None,
    search: str | None = None,
    trace_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> LogList:
    """Search ingested application logs (organization-isolated)."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    internal_client_id = (
        await _resolve_client(client_id, internal_org_id, db) if client_id else None
    )
    logs, total = await LogService(db).search_logs(
        internal_org_id,
        application=application,
        environment=environment,
        level=level,
        client_id=internal_client_id,
        search=search,
        trace_id=trace_id,
        since=since,
        until=until,
        skip=skip,
        limit=limit,
    )
    return LogList(
        logs=[LogEntryResponse.model_validate(entry) for entry in logs],
        total=total,
    )


@router.get("/stats", response_model=LogStatsResponse)
async def log_stats(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    period: str = Query(default="24h"),
    application: str | None = None,
    client_id: uuid.UUID | None = None,
) -> LogStatsResponse:
    """Aggregated log volume, error frequency, and time-bucketed chart data."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    try:
        hours = parse_period(period)
    except InvalidPeriodError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    internal_client_id = (
        await _resolve_client(client_id, internal_org_id, db) if client_id else None
    )
    stats = await LogService(db).stats(
        internal_org_id,
        hours=hours,
        application=application,
        client_id=internal_client_id,
    )
    return LogStatsResponse.model_validate(stats)


@router.delete("/retention")
async def purge_logs(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    retention_days: int = Query(default=30, ge=1, le=3650),
) -> dict[str, int]:
    """Manually purge logs older than the retention window."""
    await _resolve_org(organization_id, db, current_user)
    deleted = await LogService(db).delete_older_than(retention_days)
    return {"deleted": deleted}
