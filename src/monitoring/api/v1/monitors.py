from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from monitoring.dependencies import DbSession
from monitoring.schemas.monitor import (
    MonitorCreate,
    MonitorList,
    MonitorResponse,
    MonitorUpdate,
)
from monitoring.services.monitor_service import MonitorService

router = APIRouter()


@router.post(
    "/",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitor(
    monitor_in: MonitorCreate,
    db: DbSession,
) -> MonitorResponse:
    """Create a new monitor."""
    service = MonitorService(db)
    monitor = await service.create_monitor(monitor_in)
    return MonitorResponse.model_validate(monitor)


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
) -> MonitorResponse:
    """Get a monitor by ID."""
    service = MonitorService(db)
    monitor = await service.get_monitor(monitor_id)

    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    return MonitorResponse.model_validate(monitor)


@router.get("/", response_model=MonitorList)
async def list_monitors(
    skip: int = 0,
    limit: int = 100,
    enabled_only: bool = False,
    db: DbSession = ...,  # type: ignore[assignment]
) -> MonitorList:
    """List all monitors."""
    service = MonitorService(db)
    monitors, total = await service.list_monitors(
        skip=skip,
        limit=limit,
        enabled_only=enabled_only,
    )
    return MonitorList(
        monitors=[MonitorResponse.model_validate(m) for m in monitors],
        total=total,
    )


@router.patch("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: uuid.UUID,
    monitor_in: MonitorUpdate,
    db: DbSession,
) -> MonitorResponse:
    """Update a monitor."""
    service = MonitorService(db)
    monitor = await service.update_monitor(monitor_id, monitor_in)

    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    return MonitorResponse.model_validate(monitor)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID,
    db: DbSession,
):
    """Delete a monitor."""
    service = MonitorService(db)
    deleted = await service.delete_monitor(monitor_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
