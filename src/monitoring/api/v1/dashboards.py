from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.dashboard import (
    DashboardTemplateCreate,
    DashboardTemplateList,
    DashboardTemplateResponse,
    DashboardTemplateUpdate,
)
from monitoring.services.dashboard_service import DashboardService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()



def _dashboard_response(dashboard) -> DashboardTemplateResponse:
    return DashboardTemplateResponse(
        id=dashboard.public_id,
        name=dashboard.name,
        description=dashboard.description,
        widgets=dashboard.widgets,
        is_default=dashboard.is_default,
        created_at=dashboard.created_at,
        updated_at=dashboard.updated_at,
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


async def _dashboard_with_access(
    dashboard_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    dashboard = await DashboardService(db).get_dashboard(dashboard_id)
    if dashboard is None or not await OrganizationService(db).user_can_access(
        current_user,
        dashboard.organization_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return dashboard


@router.post("/", response_model=DashboardTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    data: DashboardTemplateCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> DashboardTemplateResponse:
    await _resolve_org(data.organization_id, db, current_user)
    try:
        dashboard = await DashboardService(db).create_dashboard(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()
    return _dashboard_response(dashboard)


@router.get("/", response_model=DashboardTemplateList)
async def list_dashboards(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> DashboardTemplateList:
    internal_org_id = await _resolve_org(organization_id, db, current_user)
    dashboards, total = await DashboardService(db).list_dashboards(
        internal_org_id,
        skip=skip,
        limit=limit,
    )
    return DashboardTemplateList(
        dashboards=[_dashboard_response(d) for d in dashboards],
        total=total,
    )


@router.get("/{dashboard_id}", response_model=DashboardTemplateResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> DashboardTemplateResponse:
    dashboard = await _dashboard_with_access(dashboard_id, db, current_user)
    return _dashboard_response(dashboard)


@router.patch("/{dashboard_id}", response_model=DashboardTemplateResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    data: DashboardTemplateUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> DashboardTemplateResponse:
    await _dashboard_with_access(dashboard_id, db, current_user)
    dashboard = await DashboardService(db).update_dashboard(dashboard_id, data)
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.commit()
    return _dashboard_response(dashboard)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _dashboard_with_access(dashboard_id, db, current_user)
    deleted = await DashboardService(db).delete_dashboard(dashboard_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
