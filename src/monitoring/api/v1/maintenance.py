from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.schemas.maintenance import (
    MaintenanceWindowCreate,
    MaintenanceWindowList,
    MaintenanceWindowResponse,
    MaintenanceWindowUpdate,
)
from monitoring.services.maintenance_service import MaintenanceService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


def _window_response(window) -> MaintenanceWindowResponse:
    return MaintenanceWindowResponse(
        id=window.public_id,
        organization_id=window.organization_id,
        title=window.title,
        description=window.description,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        notify_subscribers=window.notify_subscribers,
        monitor_ids=[association.monitor.public_id for association in window.monitors],
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


async def _ensure_org_access(
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


async def _ensure_window_access(
    window_public_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
):
    window = await MaintenanceService(db).get_window(window_public_id)
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if current_user is None or not await OrganizationService(db).user_can_access(
        current_user,
        window.organization_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return window


@router.post("/", response_model=MaintenanceWindowResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance_window(
    data: MaintenanceWindowCreate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MaintenanceWindowResponse:
    """Create a maintenance window, optionally scoped to specific monitors."""
    internal_org_id = await _ensure_org_access(data.organization_id, db, current_user)
    try:
        window = await MaintenanceService(db).create_window(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    assert internal_org_id is not None
    return _window_response(window)


@router.get("/", response_model=MaintenanceWindowList)
async def list_maintenance_windows(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> MaintenanceWindowList:
    """List maintenance windows for an organization."""
    internal_org_id = await _ensure_org_access(organization_id, db, current_user)
    windows, total = await MaintenanceService(db).list_windows(
        internal_org_id,
        skip=skip,
        limit=limit,
    )
    return MaintenanceWindowList(
        windows=[_window_response(window) for window in windows],
        total=total,
    )


@router.get("/{window_id}", response_model=MaintenanceWindowResponse)
async def get_maintenance_window(
    window_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MaintenanceWindowResponse:
    window = await _ensure_window_access(window_id, db, current_user)
    return _window_response(window)


@router.patch("/{window_id}", response_model=MaintenanceWindowResponse)
async def update_maintenance_window(
    window_id: uuid.UUID,
    data: MaintenanceWindowUpdate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> MaintenanceWindowResponse:
    await _ensure_window_access(window_id, db, current_user)
    try:
        window = await MaintenanceService(db).update_window(window_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _window_response(window)


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_window(
    window_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> Response:
    await _ensure_window_access(window_id, db, current_user)
    deleted = await MaintenanceService(db).delete_window(window_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
