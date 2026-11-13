from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.dashboard_template import DashboardTemplate
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.schemas.dashboard import DashboardTemplateCreate, DashboardTemplateUpdate

logger = structlog.get_logger(__name__)


class DashboardService:
    """CRUD for reusable dashboard templates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_dashboard(
        self,
        data: DashboardTemplateCreate,
        created_by: int | None = None,
    ) -> DashboardTemplate:
        organization = (
            await self.db.execute(
                select(Organization).where(Organization.public_id == data.organization_id),
            )
        ).scalar_one_or_none()
        if organization is None:
            raise ValueError("Organization not found")

        if data.is_default:
            await self._clear_default(organization.id)

        dashboard = DashboardTemplate(
            organization_id=organization.id,
            name=data.name,
            description=data.description,
            widgets=[widget.model_dump() for widget in data.widgets],
            is_default=data.is_default,
            created_by=created_by,
        )
        self.db.add(dashboard)
        await self.db.flush()
        await self.db.refresh(dashboard)
        return dashboard

    async def get_dashboard(
        self,
        dashboard_public_id: uuid.UUID,
    ) -> DashboardTemplate | None:
        result = await self.db.execute(
            select(DashboardTemplate).where(
                DashboardTemplate.public_id == dashboard_public_id,
            ),
        )
        return result.scalar_one_or_none()

    async def list_dashboards(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[DashboardTemplate], int]:
        base_stmt = select(DashboardTemplate).where(
            DashboardTemplate.organization_id == organization_id,
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(DashboardTemplate.created_at.desc())
            .offset(skip)
            .limit(limit),
        )
        return list(result.scalars().all()), total

    async def update_dashboard(
        self,
        dashboard_public_id: uuid.UUID,
        data: DashboardTemplateUpdate,
    ) -> DashboardTemplate | None:
        dashboard = await self.get_dashboard(dashboard_public_id)
        if dashboard is None:
            return None

        values = data.model_dump(exclude_unset=True)
        widgets = values.pop("widgets", None)
        if widgets is not None:
            dashboard.widgets = [
                widget.model_dump() if hasattr(widget, "model_dump") else widget
                for widget in widgets
            ]
        for key, value in values.items():
            setattr(dashboard, key, value)

        if data.is_default:
            await self._clear_default(dashboard.organization_id, exclude_id=dashboard.id)

        await self.db.flush()
        await self.db.refresh(dashboard)
        return dashboard

    async def delete_dashboard(self, dashboard_public_id: uuid.UUID) -> bool:
        dashboard = await self.get_dashboard(dashboard_public_id)
        if dashboard is None:
            return False
        await self.db.delete(dashboard)
        return True

    async def _clear_default(self, organization_id: int, exclude_id: int | None = None) -> None:
        stmt = select(DashboardTemplate).where(
            DashboardTemplate.organization_id == organization_id,
            DashboardTemplate.is_default.is_(True),
        )
        for dashboard in (await self.db.execute(stmt)).scalars().all():
            if exclude_id is None or dashboard.id != exclude_id:
                dashboard.is_default = False


async def resolve_monitor_public_ids(
    db: AsyncSession,
    monitor_public_ids: list[uuid.UUID],
) -> list[Monitor]:
    """Resolve monitors by public IDs (used by widget config validation)."""
    if not monitor_public_ids:
        return []
    result = await db.execute(
        select(Monitor).where(Monitor.public_id.in_(monitor_public_ids)),
    )
    return list(result.scalars().all())
