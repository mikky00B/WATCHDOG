from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from monitoring.dependencies import (
    DbSession,
    OptionalCurrentUser,
    require_api_key_scope,
)
from monitoring.models.api_key import ApiKey
from monitoring.schemas.trace import (
    TraceIngestResponse,
    TraceList,
    TraceSpanList,
    TraceSpanResponse,
)
from monitoring.services.organization_service import OrganizationService
from monitoring.services.trace_service import TraceService
from monitoring.utils.time_period import InvalidPeriodError, parse_period

router = APIRouter()
ingest_router = APIRouter()
_require_ingest_scope = require_api_key_scope("traces:write")


@ingest_router.post(
    "/ingest",
    response_model=TraceIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_traces(
    db: DbSession,
    api_key: ApiKey = Depends(_require_ingest_scope),
    body: dict | None = None,
) -> TraceIngestResponse:
    """Ingest trace spans. Accepts OTLP/JSON (`resourceSpans`) or a native
    `{"spans": [...]}` batch. Machine clients authenticate with an API key."""
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body must be a JSON object",
        )

    service = TraceService(db)
    if "resourceSpans" in body:
        accepted = await service.ingest_otlp_json(api_key.organization_id, body)
    elif isinstance(body.get("spans"), list):
        from monitoring.schemas.trace import TraceIngestRequest

        try:
            request = TraceIngestRequest.model_validate(body)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        accepted = await service.ingest_spans(api_key.organization_id, request.spans)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Body must contain 'resourceSpans' (OTLP/JSON) or 'spans'",
        )
    await db.commit()
    return TraceIngestResponse(accepted=accepted)


async def _resolve_org(
    organization_id,
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


@router.get("/", response_model=TraceList)
async def list_traces(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id,
    service: str | None = None,
    period: str = Query(default="24h"),
    limit: int = Query(default=50, ge=1, le=500),
) -> TraceList:
    """Recent traces with summary info (root span, duration, errors)."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    traces = await TraceService(db).list_traces(
        internal_org_id,
        service=service,
        hours=_hours(period),
        limit=limit,
    )
    return TraceList(traces=traces, total=len(traces))


@router.get("/service-map")
async def service_map(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id,
    period: str = Query(default="24h"),
) -> dict:
    """Service dependency edges derived from trace span parents."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    return await TraceService(db).service_map(internal_org_id, hours=_hours(period))


@router.get("/{trace_id}", response_model=TraceSpanList)
async def get_trace(
    trace_id: str,
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id,
) -> TraceSpanList:
    """All spans of one trace, ordered by start time."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    spans = await TraceService(db).get_trace(internal_org_id, trace_id)
    if not spans:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return TraceSpanList(
        spans=[TraceSpanResponse.model_validate(span) for span in spans],
        total=len(spans),
    )
