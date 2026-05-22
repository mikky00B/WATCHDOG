from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.models.check_result import CheckResult
from monitoring.schemas.check import CheckResultList, CheckResultResponse
from monitoring.services.monitor_service import MonitorService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


@router.get("/{monitor_id}/results", response_model=CheckResultList)
async def get_monitor_check_results(
    db: DbSession,
    current_user: OptionalCurrentUser,
    monitor_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> CheckResultList:
    """Get check results for a monitor."""
    # First verify monitor exists
    service = MonitorService(db)
    monitor = await service.get_monitor(monitor_id)

    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    if (
        monitor.organization_id is not None
        and (
            current_user is None
            or not await OrganizationService(db).user_can_access(
                current_user,
                monitor.organization_id,
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )

    # Base query
    base_stmt = select(CheckResult).where(CheckResult.monitor_id == monitor.id)

    # Get total count
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated check results
    stmt = (
        base_stmt.order_by(CheckResult.checked_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    check_results = list(result.scalars().all())

    return CheckResultList(
        results=[CheckResultResponse.model_validate(cr) for cr in check_results],
        total=total,
    )


@router.get("/recent", response_model=CheckResultList)
async def get_recent_check_results(
    db: DbSession,
    current_user: OptionalCurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    failed_only: bool = False,
    organization_id: uuid.UUID | None = None,
) -> CheckResultList:
    """Get recent check results across all monitors."""
    # Base query
    base_stmt = select(CheckResult)
    if failed_only:
        base_stmt = base_stmt.where(CheckResult.success == False)  # noqa: E712
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
        base_stmt = base_stmt.where(CheckResult.organization_id == organization.id)

    # Get total count
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = (
        base_stmt.order_by(CheckResult.checked_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    check_results = list(result.scalars().all())

    return CheckResultList(
        results=[CheckResultResponse.model_validate(cr) for cr in check_results],
        total=total,
    )
