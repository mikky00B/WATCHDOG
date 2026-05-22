from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.organization import (
    OrganizationCreate,
    OrganizationList,
    OrganizationResponse,
)
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> OrganizationResponse:
    service = OrganizationService(db)
    try:
        organization = await service.create_organization(data, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationResponse.model_validate(organization)


@router.get("/", response_model=OrganizationList)
async def list_organizations(
    db: DbSession,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> OrganizationList:
    service = OrganizationService(db)
    organizations, total = await service.list_user_organizations(
        current_user,
        skip=skip,
        limit=limit,
    )
    return OrganizationList(
        organizations=[OrganizationResponse.model_validate(org) for org in organizations],
        total=total,
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> OrganizationResponse:
    service = OrganizationService(db)
    organization = await service.get_organization(organization_id)
    if organization is None or not await service.user_can_access(current_user, organization.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return OrganizationResponse.model_validate(organization)

