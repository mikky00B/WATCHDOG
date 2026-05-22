from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.notification import (
    AlertEventResponse,
    NotificationChannelCreate,
    NotificationChannelList,
    NotificationChannelResponse,
    NotificationChannelUpdate,
)
from monitoring.services.notification_service import AlertEventService, NotificationChannelService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


async def _ensure_channel_access(db: DbSession, channel_id: int, current_user: CurrentUser):
    channel = await NotificationChannelService(db).get_channel(channel_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert channel {channel_id} not found",
        )
    if channel.organization_id is not None and not await OrganizationService(db).user_can_access(
        current_user,
        channel.organization_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert channel {channel_id} not found",
        )
    return channel


@router.post("/", response_model=NotificationChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_channel(
    data: NotificationChannelCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationChannelResponse:
    if data.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required",
        )
    if not await OrganizationService(db).user_can_access(current_user, data.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {data.organization_id} not found",
        )
    try:
        channel = await NotificationChannelService(db).create_channel(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return NotificationChannelResponse.model_validate(channel)


@router.get("/", response_model=NotificationChannelList)
async def list_alert_channels(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> NotificationChannelList:
    if not await OrganizationService(db).user_can_access(current_user, organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    channels, total = await NotificationChannelService(db).list_channels(
        skip=skip,
        limit=limit,
        organization_id=organization_id,
    )
    return NotificationChannelList(
        channels=[NotificationChannelResponse.model_validate(channel) for channel in channels],
        total=total,
    )


@router.get("/{channel_id}", response_model=NotificationChannelResponse)
async def get_alert_channel(
    channel_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationChannelResponse:
    channel = await _ensure_channel_access(db, channel_id, current_user)
    return NotificationChannelResponse.model_validate(channel)


@router.patch("/{channel_id}", response_model=NotificationChannelResponse)
async def update_alert_channel(
    channel_id: int,
    data: NotificationChannelUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationChannelResponse:
    await _ensure_channel_access(db, channel_id, current_user)
    try:
        channel = await NotificationChannelService(db).update_channel(channel_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return NotificationChannelResponse.model_validate(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_channel(
    channel_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _ensure_channel_access(db, channel_id, current_user)
    await NotificationChannelService(db).delete_channel(channel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{channel_id}/test", response_model=AlertEventResponse)
async def test_alert_channel(
    channel_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> AlertEventResponse:
    channel = await _ensure_channel_access(db, channel_id, current_user)
    event = await AlertEventService(db, cooldown_minutes=0).queue_event(
        organization_id=channel.organization_id,
        monitor_id=None,
        incident_id=None,
        channel_id=channel.id,
        event_type="TEST",
        message=f"Test alert for {channel.name}",
    )
    return AlertEventResponse.model_validate(event)

