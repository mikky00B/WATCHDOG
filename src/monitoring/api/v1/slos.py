from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.slo import SLOCreate, SLOList, SLOResponse, SLOStatus, SLOUpdate
from monitoring.services.organization_service import OrganizationService
from monitoring.services.slo_service import SLOService

router = APIRouter()



def _slo_response(slo) -> SLOResponse:
    return SLOResponse(
        id=slo.public_id,
        monitor_id=slo.monitor_id,
        name=slo.name,
        description=slo.description,
        target_percentage=slo.target_percentage,
        window_days=slo.window_days,
        created_at=slo.created_at,
        updated_at=slo.updated_at,
    )


async def _resolve_org(
    organization_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> int:
    organization = await OrganizationService(db).get_organization(organization_id)
    if organization is None or not await OrganizationService(db).user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization.id


async def _slo_with_access(slo_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    slo = await SLOService(db).get_slo(slo_id)
    if slo is None or not await OrganizationService(db).user_can_access(
        current_user,
        slo.organization_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return slo


@router.post("/", response_model=SLOResponse, status_code=status.HTTP_201_CREATED)
async def create_slo(
    data: SLOCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> SLOResponse:
    await _resolve_org(data.organization_id, db, current_user)
    try:
        slo = await SLOService(db).create_slo(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()
    return _slo_response(slo)


@router.get("/", response_model=SLOList)
async def list_slos(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> SLOList:
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    slos, total = await SLOService(db).list_slos(internal_org_id, skip=skip, limit=limit)
    return SLOList(slos=[_slo_response(slo) for slo in slos], total=total)


@router.get("/{slo_id}", response_model=SLOResponse)
async def get_slo(
    slo_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> SLOResponse:
    slo = await _slo_with_access(slo_id, db, current_user)
    return _slo_response(slo)


@router.get("/{slo_id}/status", response_model=SLOStatus)
async def get_slo_status(
    slo_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> SLOStatus:
    """Computed attainment and error budget for one SLO."""
    slo = await _slo_with_access(slo_id, db, current_user)
    status_data = await SLOService(db).compute_status(slo)
    return SLOStatus.model_validate(status_data)


@router.patch("/{slo_id}", response_model=SLOResponse)
async def update_slo(
    slo_id: uuid.UUID,
    data: SLOUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> SLOResponse:
    await _slo_with_access(slo_id, db, current_user)
    slo = await SLOService(db).update_slo(slo_id, data)
    if slo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.commit()
    return _slo_response(slo)


@router.delete("/{slo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slo(
    slo_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _slo_with_access(slo_id, db, current_user)
    deleted = await SLOService(db).delete_slo(slo_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
