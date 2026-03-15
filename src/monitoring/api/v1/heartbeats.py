from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import DbSession
from monitoring.schemas.heartbeat import (
    HeartbeatCreate,
    HeartbeatList,
    HeartbeatResponse,
    HeartbeatUpdate,
)
from monitoring.services.heartbeat_service import HeartbeatService

router = APIRouter()


@router.post(
    "/",
    response_model=HeartbeatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_heartbeat(
    heartbeat_in: HeartbeatCreate,
    db: DbSession,
) -> HeartbeatResponse:
    """Create a new heartbeat."""
    service = HeartbeatService(db)
    heartbeat = await service.create_heartbeat(heartbeat_in)
    return HeartbeatResponse.model_validate(heartbeat)


@router.get("/{heartbeat_id}", response_model=HeartbeatResponse)
async def get_heartbeat(
    heartbeat_id: uuid.UUID,
    db: DbSession,
) -> HeartbeatResponse:
    """Get a heartbeat by ID."""
    service = HeartbeatService(db)
    heartbeat = await service.get_heartbeat(heartbeat_id)

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Heartbeat {heartbeat_id} not found",
        )

    return HeartbeatResponse.model_validate(heartbeat)


@router.get("/", response_model=HeartbeatList)
async def list_heartbeats(
    db: DbSession,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> HeartbeatList:
    """List all heartbeats."""
    service = HeartbeatService(db)
    heartbeats, total = await service.list_heartbeats(
        skip=skip, limit=limit
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
) -> HeartbeatResponse:
    """Update a heartbeat."""
    service = HeartbeatService(db)
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
) -> Response:
    """Delete a heartbeat."""
    service = HeartbeatService(db)
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
