from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from monitoring.dependencies import DbSession
from monitoring.models.check_result import CheckResult
from monitoring.schemas.check import CheckResultList, CheckResultResponse
from monitoring.services.monitor_service import MonitorService

router = APIRouter()


@router.get("/{monitor_id}/results", response_model=CheckResultList)
async def get_monitor_check_results(
    monitor_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: DbSession = ...,
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
    skip: int = 0,
    limit: int = 100,
    failed_only: bool = False,
    db: DbSession = ...,
) -> CheckResultList:
    """Get recent check results across all monitors."""
    # Base query
    base_stmt = select(CheckResult)
    if failed_only:
        base_stmt = base_stmt.where(CheckResult.success == False)  # noqa: E712

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
