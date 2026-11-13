from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.models.slo import SLO
from monitoring.schemas.slo import SLOCreate, SLOUpdate

logger = structlog.get_logger(__name__)


class SLOService:
    """Service level objectives with error-budget tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_slo(self, data: SLOCreate) -> SLO:
        organization = (
            await self.db.execute(
                select(Organization).where(Organization.public_id == data.organization_id),
            )
        ).scalar_one_or_none()
        if organization is None:
            raise ValueError("Organization not found")
        monitor = (
            await self.db.execute(
                select(Monitor).where(Monitor.public_id == data.monitor_id),
            )
        ).scalar_one_or_none()
        if monitor is None or monitor.organization_id != organization.id:
            raise ValueError("Monitor not found")

        slo = SLO(
            organization_id=organization.id,
            monitor_id=monitor.id,
            name=data.name,
            description=data.description,
            target_percentage=data.target_percentage,
            window_days=data.window_days,
        )
        self.db.add(slo)
        await self.db.flush()
        await self.db.refresh(slo)
        return slo

    async def get_slo(self, slo_public_id: uuid.UUID) -> SLO | None:
        result = await self.db.execute(select(SLO).where(SLO.public_id == slo_public_id))
        return result.scalar_one_or_none()

    async def list_slos(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[SLO], int]:
        base_stmt = select(SLO).where(SLO.organization_id == organization_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(SLO.created_at.desc()).offset(skip).limit(limit),
        )
        return list(result.scalars().all()), total

    async def update_slo(
        self,
        slo_public_id: uuid.UUID,
        data: SLOUpdate,
    ) -> SLO | None:
        slo = await self.get_slo(slo_public_id)
        if slo is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(slo, key, value)
        await self.db.flush()
        await self.db.refresh(slo)
        return slo

    async def delete_slo(self, slo_public_id: uuid.UUID) -> bool:
        slo = await self.get_slo(slo_public_id)
        if slo is None:
            return False
        await self.db.delete(slo)
        return True

    async def compute_status(self, slo: SLO) -> dict[str, object]:
        """Attainment and error-budget state over the SLO window."""
        monitor = await self.db.get(Monitor, slo.monitor_id)
        now = datetime.now(UTC)
        period_start = now - timedelta(days=slo.window_days)

        total = (
            await self.db.execute(
                select(func.count()).select_from(
                    select(CheckResult.id)
                    .where(
                        CheckResult.monitor_id == slo.monitor_id,
                        CheckResult.checked_at >= period_start,
                    )
                    .subquery(),
                ),
            )
        ).scalar() or 0
        successful = (
            await self.db.execute(
                select(func.count()).select_from(
                    select(CheckResult.id)
                    .where(
                        CheckResult.monitor_id == slo.monitor_id,
                        CheckResult.checked_at >= period_start,
                        CheckResult.success.is_(True),
                    )
                    .subquery(),
                ),
            )
        ).scalar() or 0

        attained = round((successful / total) * 100, 3) if total else 0.0

        window_minutes = slo.window_days * 24 * 60
        allowed_downtime_minutes = window_minutes * (1 - slo.target_percentage / 100)
        used_downtime_minutes = window_minutes * (1 - attained / 100)
        remaining_percentage = 0.0
        if allowed_downtime_minutes > 0:
            remaining_percentage = round(
                max(
                    0.0,
                    (allowed_downtime_minutes - used_downtime_minutes)
                    / allowed_downtime_minutes
                    * 100,
                ),
                2,
            )

        return {
            "slo_id": slo.public_id,
            "name": slo.name,
            "monitor_public_id": monitor.public_id if monitor else None,
            "monitor_name": monitor.name if monitor else "unknown",
            "target_percentage": slo.target_percentage,
            "window_days": slo.window_days,
            "period_start": period_start,
            "period_end": now,
            "total_checks": total,
            "successful_checks": successful,
            "attained_percentage": attained,
            "target_met": attained >= slo.target_percentage,
            "error_budget_minutes": round(allowed_downtime_minutes, 1),
            "error_budget_used_minutes": round(max(0.0, used_downtime_minutes), 1),
            "error_budget_remaining_percentage": remaining_percentage,
        }
