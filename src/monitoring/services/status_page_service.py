from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from monitoring.models.check_result import CheckResult
from monitoring.models.incident import Incident
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.models.status_page import StatusPage
from monitoring.models.status_page import StatusPageService as StatusPageServiceModel
from monitoring.schemas.status_page import (
    StatusPageCreate,
    StatusPageServiceCreate,
    StatusPageUpdate,
)


class StatusPageService:
    """Business logic for public status pages."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_status_page(self, data: StatusPageCreate) -> StatusPage:
        organization = await self._get_organization(data.organization_id)
        if organization is None:
            raise ValueError("Organization not found")
        existing = await self.get_status_page_by_slug(data.slug)
        if existing is not None:
            raise ValueError("Status page slug is already in use")

        status_page = StatusPage(
            organization_id=organization.id,
            name=data.name,
            slug=data.slug,
            logo_url=str(data.logo_url) if data.logo_url is not None else None,
            brand_color=data.brand_color,
            is_active=data.is_active,
        )
        self.db.add(status_page)
        await self.db.flush()
        await self.db.refresh(status_page)
        return status_page

    async def _get_organization(self, organization_id: uuid.UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(Organization.public_id == organization_id),
        )
        return result.scalar_one_or_none()

    async def get_status_page(self, status_page_id: uuid.UUID) -> StatusPage | None:
        result = await self.db.execute(
            select(StatusPage).where(StatusPage.public_id == status_page_id),
        )
        return result.scalar_one_or_none()

    async def get_status_page_by_slug(self, slug: str) -> StatusPage | None:
        result = await self.db.execute(select(StatusPage).where(StatusPage.slug == slug))
        return result.scalar_one_or_none()

    async def list_status_pages(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[StatusPage], int]:
        base_stmt = select(StatusPage).where(StatusPage.organization_id == organization_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(StatusPage.created_at.desc()).offset(skip).limit(limit),
        )
        return list(result.scalars().all()), total

    async def update_status_page(
        self,
        status_page_id: uuid.UUID,
        data: StatusPageUpdate,
    ) -> StatusPage | None:
        status_page = await self.get_status_page(status_page_id)
        if status_page is None:
            return None

        if data.slug is not None and data.slug != status_page.slug:
            existing = await self.get_status_page_by_slug(data.slug)
            if existing is not None:
                raise ValueError("Status page slug is already in use")

        for key, value in data.model_dump(exclude_unset=True).items():
            if key == "logo_url" and value is not None:
                value = str(value)
            setattr(status_page, key, value)

        await self.db.flush()
        await self.db.refresh(status_page)
        return status_page

    async def delete_status_page(self, status_page_id: uuid.UUID) -> bool:
        status_page = await self.get_status_page(status_page_id)
        if status_page is None:
            return False

        await self.db.delete(status_page)
        return True

    async def add_service(
        self,
        status_page_id: uuid.UUID,
        data: StatusPageServiceCreate,
    ) -> StatusPageServiceModel | None:
        status_page = await self.get_status_page(status_page_id)
        if status_page is None:
            return None

        monitor = (
            await self.db.execute(select(Monitor).where(Monitor.public_id == data.monitor_id))
        ).scalar_one_or_none()
        if monitor is None or monitor.organization_id != status_page.organization_id:
            raise ValueError("Monitor not found")

        service = StatusPageServiceModel(
            status_page_id=status_page.id,
            monitor_id=monitor.id,
            display_name=data.display_name,
            sort_order=data.sort_order,
            is_visible=data.is_visible,
        )
        self.db.add(service)
        await self.db.flush()
        await self.db.refresh(service)
        return service

    async def list_services(
        self,
        status_page_id: uuid.UUID,
    ) -> tuple[list[StatusPageServiceModel], int] | None:
        status_page = await self.get_status_page(status_page_id)
        if status_page is None:
            return None

        stmt = select(StatusPageServiceModel).where(
            StatusPageServiceModel.status_page_id == status_page.id,
        )
        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            stmt.order_by(StatusPageServiceModel.sort_order.asc(), StatusPageServiceModel.id.asc()),
        )
        return list(result.scalars().all()), total

    async def delete_service(
        self,
        status_page_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> bool:
        status_page = await self.get_status_page(status_page_id)
        if status_page is None:
            return False

        service = (
            await self.db.execute(
                select(StatusPageServiceModel).where(
                    StatusPageServiceModel.public_id == service_id,
                    StatusPageServiceModel.status_page_id == status_page.id,
                ),
            )
        ).scalar_one_or_none()
        if service is None:
            return False

        await self.db.delete(service)
        return True

    async def get_public_status_page(self, slug: str) -> dict[str, object] | None:
        status_page = (
            await self.db.execute(
                select(StatusPage)
                .options(selectinload(StatusPage.services))
                .where(StatusPage.slug == slug, StatusPage.is_active.is_(True)),
            )
        ).scalar_one_or_none()
        if status_page is None:
            return None

        services = []
        overall_status = "OPERATIONAL"
        visible_services = sorted(
            [service for service in status_page.services if service.is_visible],
            key=lambda service: service.sort_order,
        )
        for service in visible_services:
            monitor = await self.db.get(Monitor, service.monitor_id)
            if monitor is None:
                continue
            uptime = await self._uptime_percentage(monitor.id)
            services.append(
                {
                    "id": service.id,
                    "display_name": service.display_name,
                    "status": monitor.status,
                    "uptime_30d": uptime,
                }
            )
            if monitor.status == "DOWN":
                overall_status = "MAJOR_OUTAGE"
            elif monitor.status == "DEGRADED" and overall_status != "MAJOR_OUTAGE":
                overall_status = "DEGRADED"

        active_incidents = await self._incident_payloads(status_page.organization_id, active=True)
        recent_incidents = await self._incident_payloads(status_page.organization_id, active=False)

        return {
            "name": status_page.name,
            "slug": status_page.slug,
            "logo_url": status_page.logo_url,
            "brand_color": status_page.brand_color,
            "overall_status": overall_status,
            "services": services,
            "active_incidents": active_incidents,
            "recent_incidents": recent_incidents,
            "maintenance_windows": [],
        }

    async def _uptime_percentage(self, monitor_id: int) -> float:
        base_stmt = select(CheckResult).where(CheckResult.monitor_id == monitor_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        if total == 0:
            return 0.0
        successes = (
            await self.db.execute(
                select(func.count()).select_from(
                    base_stmt.where(CheckResult.success.is_(True)).subquery(),
                ),
            )
        ).scalar() or 0
        return round((successes / total) * 100, 2)

    async def _incident_payloads(
        self,
        organization_id: int,
        active: bool,
    ) -> list[dict[str, object]]:
        stmt = select(Incident).where(Incident.organization_id == organization_id)
        if active:
            stmt = stmt.where(Incident.status.in_(["OPEN", "ACKNOWLEDGED"]))
        else:
            stmt = stmt.where(Incident.status == "RESOLVED")
        result = await self.db.execute(stmt.order_by(Incident.started_at.desc()).limit(10))
        return [
            {
                "id": incident.id,
                "monitor_id": incident.monitor_id,
                "title": incident.title,
                "status": incident.status,
                "severity": incident.severity,
                "started_at": incident.started_at,
                "resolved_at": incident.resolved_at,
            }
            for incident in result.scalars().all()
        ]
