from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.schemas.alert import AlertList, AlertResponse, AlertUpdate
from monitoring.services.alert_service import AlertService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


@router.get("/", response_model=AlertList)
async def list_alerts(
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    unresolved_only: bool = False,
    organization_id: uuid.UUID | None = None,
) -> AlertList:
    """List alerts."""
    service = AlertService(db)
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
    alerts, total = await service.list_alerts(
        skip=skip,
        limit=limit,
        unresolved_only=unresolved_only,
        organization_id=internal_organization_id,
    )

    return AlertList(
        alerts=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> AlertResponse:
    """Get an alert by ID."""
    service = AlertService(db)
    alert = await service.get_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    if (
        alert.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                alert.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    alert_in: AlertUpdate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> AlertResponse:
    """Update an alert."""
    service = AlertService(db)
    existing = await service.get_alert(alert_id)
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
            detail=f"Alert {alert_id} not found",
        )
    alert = await service.update_alert(alert_id, alert_in)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> AlertResponse:
    """Resolve an alert."""
    service = AlertService(db)
    existing = await service.get_alert(alert_id)
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
            detail=f"Alert {alert_id} not found",
        )
    alert = await service.resolve_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> AlertResponse:
    """Acknowledge an alert."""
    service = AlertService(db)
    existing = await service.get_alert(alert_id)
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
            detail=f"Alert {alert_id} not found",
        )
    alert = await service.acknowledge_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)
