from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.models.monitor import Monitor
from monitoring.schemas.check import CheckResultList, CheckResultResponse
from monitoring.schemas.monitor import (
    MonitorCreate,
    MonitorList,
    MonitorResponse,
    MonitorStats,
    MonitorUpdate,
)
from monitoring.services.monitor_service import MonitorService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


def _monitor_response(monitor: Monitor) -> MonitorResponse:
    response = MonitorResponse.model_validate(monitor)
    if monitor.heartbeat_key:
        response.heartbeat_url = f"/api/v1/monitors/heartbeat/{monitor.heartbeat_key}"
    return response


async def _ensure_monitor_access(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> Monitor:
    monitor = await MonitorService(db).get_monitor(monitor_id)
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
    if (
        monitor.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                monitor.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
    return monitor


@router.post(
    "/",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitor(
    monitor_in: MonitorCreate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorResponse:
    """Create a new monitor."""
    service = MonitorService(db)
    if monitor_in.organization_id is not None:
        organization = await OrganizationService(db).get_organization(monitor_in.organization_id)
        if (
            organization is None
            or current_user is None
            or not await OrganizationService(db).user_can_access(current_user, organization.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Organization {monitor_in.organization_id} not found",
            )
    try:
        monitor = await service.create_monitor(monitor_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _monitor_response(monitor)


@router.post("/heartbeat/{heartbeat_key}", response_model=MonitorResponse)
async def ping_heartbeat_monitor(
    heartbeat_key: str,
    db: DbSession,
) -> MonitorResponse:
    service = MonitorService(db)
    monitor = await service.ping_heartbeat_monitor(heartbeat_key)
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat monitor {heartbeat_key} not found",
        )
    return _monitor_response(monitor)


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorResponse:
    """Get a monitor by ID."""
    monitor = await _ensure_monitor_access(monitor_id, db, current_user)

    return _monitor_response(monitor)


@router.get("/{monitor_id}/checks", response_model=CheckResultList)
async def get_monitor_checks(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> CheckResultList:
    await _ensure_monitor_access(monitor_id, db, current_user)
    results = await MonitorService(db).list_check_results(
        monitor_id,
        skip=skip,
        limit=limit,
    )
    if results is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    check_results, total = results
    return CheckResultList(
        results=[CheckResultResponse.model_validate(result) for result in check_results],
        total=total,
    )


@router.get("/{monitor_id}/stats", response_model=MonitorStats)
async def get_monitor_stats(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorStats:
    await _ensure_monitor_access(monitor_id, db, current_user)
    stats_data = await MonitorService(db).get_stats(monitor_id)
    if stats_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return MonitorStats.model_validate(stats_data)


@router.post("/{monitor_id}/pause", response_model=MonitorResponse)
async def pause_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorResponse:
    await _ensure_monitor_access(monitor_id, db, current_user)
    monitor = await MonitorService(db).pause_monitor(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _monitor_response(monitor)


@router.post("/{monitor_id}/resume", response_model=MonitorResponse)
async def resume_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorResponse:
    await _ensure_monitor_access(monitor_id, db, current_user)
    monitor = await MonitorService(db).resume_monitor(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _monitor_response(monitor)


@router.post("/{monitor_id}/run-check", response_model=CheckResultResponse)
async def run_monitor_check(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> CheckResultResponse:
    await _ensure_monitor_access(monitor_id, db, current_user)
    check_result = await MonitorService(db).run_check_now(monitor_id)
    if check_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return CheckResultResponse.model_validate(check_result)


@router.get("/", response_model=MonitorList)
async def list_monitors(
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    enabled_only: bool = False,
    organization_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
) -> MonitorList:
    """List all monitors."""
    service = MonitorService(db)
    internal_organization_id = None
    if organization_id is not None:
        organization_service = OrganizationService(db)
        organization = await organization_service.get_organization(organization_id)
        if (
            organization is None
            or current_user is None
            or not await organization_service.user_can_access(current_user, organization.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Organization {organization_id} not found",
            )
        internal_organization_id = organization.id
    internal_client_id = None
    if client_id is not None:
        client = await service.get_client_by_public_id(client_id)
        if (
            client is None
            or internal_organization_id is None
            or client.organization_id != internal_organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {client_id} not found",
            )
        internal_client_id = client.id
    monitors, total = await service.list_monitors(
        skip=skip,
        limit=limit,
        enabled_only=enabled_only,
        organization_id=internal_organization_id,
        client_id=internal_client_id,
    )
    return MonitorList(
        monitors=[_monitor_response(m) for m in monitors],
        total=total,
    )


@router.patch("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: uuid.UUID,
    monitor_in: MonitorUpdate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MonitorResponse:
    """Update a monitor."""
    service = MonitorService(db)
    existing = await service.get_monitor(monitor_id)
    if (
        existing is not None
        and existing.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                existing.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
    monitor = await service.update_monitor(monitor_id, monitor_in)

    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    return _monitor_response(monitor)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> Response:
    """Delete a monitor."""
    service = MonitorService(db)
    existing = await service.get_monitor(monitor_id)
    if (
        existing is not None
        and existing.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                existing.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
    deleted = await service.delete_monitor(monitor_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
