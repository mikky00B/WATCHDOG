from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from monitoring.dependencies import (
    DbSession,
    OptionalCurrentUser,
    require_api_key_scope,
)
from monitoring.models.api_key import ApiKey
from monitoring.schemas.infrastructure import (
    HostThresholdCreate,
    HostThresholdList,
    HostThresholdResponse,
    HostThresholdUpdate,
    InfraIngestRequest,
    InfraIngestResponse,
    InfraSummary,
)
from monitoring.services.infrastructure_service import (
    InfrastructureService,
    resolve_client,
)
from monitoring.services.organization_service import OrganizationService

router = APIRouter()
ingest_router = APIRouter()
_require_ingest_scope = require_api_key_scope("metrics:write")


@ingest_router.post(
    "/ingest",
    response_model=InfraIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_host_metrics(
    payload: InfraIngestRequest,
    db: DbSession,
    api_key: ApiKey = Depends(_require_ingest_scope),
) -> InfraIngestResponse:
    """Ingest host metrics from the WATCHDOG agent (API key auth)."""
    accepted = await InfrastructureService(db).ingest_metrics(
        api_key.organization_id,
        payload.metrics,
    )
    await db.commit()
    return InfraIngestResponse(accepted=accepted)


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


@router.get("/hosts", response_model=InfraSummary)
async def list_hosts(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    client_id: uuid.UUID | None = None,
    history_hours: float = Query(default=6.0, gt=0, le=24 * 30),
) -> InfraSummary:
    """Latest host health, recent metric history, and configured thresholds."""
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    if client_id is not None:
        client = await resolve_client(db, client_id)
        if client is None or client.organization_id != internal_org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {client_id} not found",
            )
    hosts = await InfrastructureService(db).list_hosts(
        internal_org_id,
        history_hours=history_hours,
    )
    return InfraSummary(hosts=hosts, total_hosts=len(hosts))


@router.get("/thresholds", response_model=HostThresholdList)
async def list_thresholds(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
) -> HostThresholdList:
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    thresholds = await InfrastructureService(db).list_thresholds(internal_org_id)
    return HostThresholdList(
        thresholds=[HostThresholdResponse.model_validate(t) for t in thresholds],
        total=len(thresholds),
    )


@router.post(
    "/thresholds",
    response_model=HostThresholdResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_threshold(
    data: HostThresholdCreate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> HostThresholdResponse:
    internal_org_id = await _resolve_org(data.organization_id, db, current_user)
    threshold = await InfrastructureService(db).upsert_threshold(internal_org_id, data)
    await db.commit()
    return HostThresholdResponse.model_validate(threshold)


@router.patch("/thresholds/{threshold_id}", response_model=HostThresholdResponse)
async def update_threshold(
    threshold_id: int,
    data: HostThresholdUpdate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> HostThresholdResponse:
    await db_threshold_access(db, current_user, threshold_id)
    updated = await InfrastructureService(db).update_threshold(threshold_id, data)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.commit()
    return HostThresholdResponse.model_validate(updated)


@router.delete("/thresholds/{threshold_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_threshold(
    threshold_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> Response:
    await db_threshold_access(db, current_user, threshold_id)
    deleted = await InfrastructureService(db).delete_threshold(threshold_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def db_threshold_access(db: DbSession, current_user: OptionalCurrentUser, threshold_id: int):
    from monitoring.models.host_metric import HostThreshold

    threshold = await db.get(HostThreshold, threshold_id)
    if (
        threshold is None
        or current_user is None
        or not await OrganizationService(db).user_can_access(
            current_user,
            threshold.organization_id,
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return threshold
