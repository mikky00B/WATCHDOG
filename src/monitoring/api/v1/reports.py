from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.report import MonthlyReportResponse
from monitoring.services.organization_service import OrganizationService
from monitoring.services.report_service import ReportService

router = APIRouter()


async def _ensure_organization_access(
    db: DbSession,
    organization_id: uuid.UUID,
    current_user: CurrentUser,
):
    organization_service = OrganizationService(db)
    organization = await organization_service.get_organization(organization_id)
    if organization is None or not await organization_service.user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization


@router.get("/monthly", response_model=MonthlyReportResponse)
async def get_monthly_report(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    client_id: uuid.UUID | None = None,
) -> MonthlyReportResponse:
    await _ensure_organization_access(db, organization_id, current_user)
    report = await ReportService(db).generate_monthly_report(
        organization_id=organization_id,
        client_id=client_id,
        year=year,
        month=month,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report scope not found",
        )
    return report


@router.get("/monthly/html", response_class=HTMLResponse)
async def get_monthly_report_html(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    client_id: uuid.UUID | None = None,
) -> HTMLResponse:
    await _ensure_organization_access(db, organization_id, current_user)
    service = ReportService(db)
    report = await service.generate_monthly_report(
        organization_id=organization_id,
        client_id=client_id,
        year=year,
        month=month,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report scope not found",
        )
    return HTMLResponse(service.render_monthly_report_html(report))
