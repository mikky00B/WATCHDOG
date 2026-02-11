from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from monitoring.dependencies import DbSession
from monitoring.schemas.alert import AlertList, AlertResponse, AlertUpdate
from monitoring.services.alert_service import AlertService

router = APIRouter()


@router.get("/", response_model=AlertList)
async def list_alerts(
    skip: int = 0,
    limit: int = 100,
    unresolved_only: bool = False,
    db: DbSession = ...,
) -> AlertList:
    """List alerts."""
    service = AlertService(db)
    alerts, total = await service.list_alerts(
        skip=skip,
        limit=limit,
        unresolved_only=unresolved_only,
    )

    return AlertList(
        alerts=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: DbSession,
) -> AlertResponse:
    """Get an alert by ID."""
    service = AlertService(db)
    alert = await service.get_alert(alert_id)

    if alert is None:
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
) -> AlertResponse:
    """Update an alert."""
    service = AlertService(db)
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
) -> AlertResponse:
    """Resolve an alert."""
    service = AlertService(db)
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
) -> AlertResponse:
    """Acknowledge an alert."""
    service = AlertService(db)
    alert = await service.acknowledge_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)
