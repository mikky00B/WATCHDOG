"""Legacy standalone heartbeat endpoints.

The product-facing heartbeat path is now heartbeat-type Monitor records:
create a monitor with ``monitor_type="HEARTBEAT"`` and ping the returned
``/api/v1/monitors/heartbeat/{heartbeat_key}`` URL. These standalone heartbeat
records are kept as a deprecated legacy API until old clients are migrated.
They do not create incidents, alerts, or status-page services.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.schemas.heartbeat import (
    HeartbeatCreate,
    HeartbeatList,
    HeartbeatResponse,
    HeartbeatUpdate,
)
from monitoring.services.heartbeat_service import HeartbeatService
from monitoring.services.organization_service import OrganizationService

router = APIRouter(deprecated=True)


@router.post(
    "/",
    response_model=HeartbeatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_heartbeat(
    heartbeat_in: HeartbeatCreate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> HeartbeatResponse:
    """Create a new heartbeat."""
    service = HeartbeatService(db)
    if heartbeat_in.organization_id is not None:
        organization_service = OrganizationService(db)
        organization = await organization_service.get_organization(
            heartbeat_in.organization_id,
        )
        if (
            organization is None
            or current_user is None
            or not await organization_service.user_can_access(current_user, organization.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Organization {heartbeat_in.organization_id} not found",
            )
    try:
        heartbeat = await service.create_heartbeat(heartbeat_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return HeartbeatResponse.model_validate(heartbeat)


@router.get("/{heartbeat_id}", response_model=HeartbeatResponse)
async def get_heartbeat(
    heartbeat_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> HeartbeatResponse:
    """Get a heartbeat by ID."""
    service = HeartbeatService(db)
    heartbeat = await service.get_heartbeat(heartbeat_id)

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )
    if (
        heartbeat.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                heartbeat.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )

    return HeartbeatResponse.model_validate(heartbeat)


@router.get("/", response_model=HeartbeatList)
async def list_heartbeats(
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    organization_id: uuid.UUID | None = None,
) -> HeartbeatList:
    """List all heartbeats."""
    service = HeartbeatService(db)
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
    heartbeats, total = await service.list_heartbeats(
        skip=skip,
        limit=limit,
        organization_id=internal_organization_id,
    )  # ← Unpack the tuple
    return HeartbeatList(
        heartbeats=[HeartbeatResponse.model_validate(h) for h in heartbeats],
        total=total,
    )


@router.patch("/{heartbeat_id}", response_model=HeartbeatResponse)
async def update_heartbeat(
    heartbeat_id: uuid.UUID,
    heartbeat_in: HeartbeatUpdate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> HeartbeatResponse:
    """Update a heartbeat."""
    service = HeartbeatService(db)
    existing = await service.get_heartbeat(heartbeat_id)
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
            detail=f"Heartbeat {heartbeat_id} not found",
        )
    heartbeat = await service.update_heartbeat(heartbeat_id, heartbeat_in)

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )

    return HeartbeatResponse.model_validate(heartbeat)


@router.delete("/{heartbeat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_heartbeat(
    heartbeat_id: uuid.UUID,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> Response:
    """Delete a heartbeat."""
    service = HeartbeatService(db)
    existing = await service.get_heartbeat(heartbeat_id)
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
            detail=f"Heartbeat {heartbeat_id} not found",
        )
    deleted = await service.delete_heartbeat(heartbeat_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{heartbeat_id}/ping", response_model=HeartbeatResponse)
async def ping_heartbeat(
    heartbeat_id: uuid.UUID,
    db: DbSession,
) -> HeartbeatResponse:
    """Record a heartbeat ping."""
    service = HeartbeatService(db)
    heartbeat = await service.ping_heartbeat(heartbeat_id)

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )

    return HeartbeatResponse.model_validate(heartbeat)
