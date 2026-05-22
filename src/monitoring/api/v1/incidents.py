from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.schemas.incident import (
    IncidentList,
    IncidentResponse,
    IncidentUpdateCreate,
    IncidentUpdateResponse,
)
from monitoring.services.incident_service import IncidentService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


async def _get_authorized_organization_id(
    db: DbSession,
    organization_id: uuid.UUID | None,
    current_user: OptionalCurrentUser,
) -> int | None:
    if organization_id is None:
        return None

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
    return organization.id


async def _ensure_incident_access(
    db: DbSession,
    incident_id: int,
    current_user: OptionalCurrentUser,
):
    incident = await IncidentService(db).get_incident(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    if (
        incident.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                incident.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return incident


@router.get("/", response_model=IncidentList)
async def list_incidents(
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    status_filter: str | None = Query(default=None, alias="status"),
    organization_id: uuid.UUID | None = None,
) -> IncidentList:
    internal_organization_id = await _get_authorized_organization_id(
        db,
        organization_id,
        current_user,
    )
    incidents, total = await IncidentService(db).list_incidents(
        skip=skip,
        limit=limit,
        status=status_filter,
        organization_id=internal_organization_id,
    )
    return IncidentList(
        incidents=[IncidentResponse.model_validate(incident) for incident in incidents],
        total=total,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> IncidentResponse:
    incident = await _ensure_incident_access(db, incident_id, current_user)
    return IncidentResponse.model_validate(incident)


@router.post("/{incident_id}/acknowledge", response_model=IncidentResponse)
async def acknowledge_incident(
    incident_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
    note: str | None = None,
) -> IncidentResponse:
    await _ensure_incident_access(db, incident_id, current_user)
    incident = await IncidentService(db).acknowledge_incident(
        incident_id,
        user=current_user,
        note=note,
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return IncidentResponse.model_validate(incident)


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: int,
    db: DbSession,
    current_user: OptionalCurrentUser,
    note: str | None = None,
) -> IncidentResponse:
    await _ensure_incident_access(db, incident_id, current_user)
    incident = await IncidentService(db).resolve_incident(
        incident_id,
        note=note,
        user=current_user,
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return IncidentResponse.model_validate(incident)


@router.post("/{incident_id}/updates", response_model=IncidentUpdateResponse)
async def add_incident_update(
    incident_id: int,
    data: IncidentUpdateCreate,
    db: DbSession,
    current_user: OptionalCurrentUser,
) -> IncidentUpdateResponse:
    await _ensure_incident_access(db, incident_id, current_user)
    update = await IncidentService(db).add_update_from_schema(
        incident_id,
        data,
        user=current_user,
    )
    if update is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return IncidentUpdateResponse.model_validate(update)

