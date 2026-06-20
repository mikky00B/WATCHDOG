from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from monitoring.api.v1 import (
    alert_channels,
    alerts,
    auth,
    checks,
    clients,
    heartbeats,
    incidents,
    monitors,
    organizations,
    reports,
    status_pages,
)
from monitoring.api.v1.integrations import telegram as telegram_integration
from monitoring.config import get_settings
from monitoring.database import close_db, init_db
from monitoring.dependencies import DbSession, OptionalCurrentUser
from monitoring.models.alert import Alert
from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.services.checker_service import CheckerService
from monitoring.services.organization_service import OrganizationService
from monitoring.services.rule_engine import RuleEngine
from monitoring.utils.logging import get_logger, setup_logging
from monitoring.workers.notification_worker import NotificationWorker
from monitoring.workers.scheduler import MonitorScheduler

# Setup logging
setup_logging()
logger = get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan events.

    Handles startup and shutdown tasks.
    """
    logger.info("application_startup")

    if settings.auto_create_tables:
        # Development convenience only. Production schema creation must use Alembic.
        await init_db()
        logger.info("database_auto_create_tables_completed")
    scheduler: MonitorScheduler | None = None
    scheduler_task: asyncio.Task[None] | None = None
    notification_worker = NotificationWorker(settings=settings)
    notification_worker_task = asyncio.create_task(notification_worker.start())
    logger.info("api_notification_worker_started")
    if settings.run_scheduler_in_api:
        scheduler = MonitorScheduler(
            checker_service=CheckerService(
                max_concurrent=settings.max_concurrent_checks,
                requests_per_minute=settings.requests_per_minute_per_site,
                max_retries=settings.max_check_retries,
            ),
            rule_engine=RuleEngine(),
        )
        scheduler_task = asyncio.create_task(scheduler.start())
        logger.info("api_scheduler_started")

    try:
        yield
    finally:
        await notification_worker.stop()
        notification_worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await notification_worker_task
        if scheduler is not None:
            await scheduler.stop()
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task

        # Cleanup
        await close_db()
        logger.info("application_shutdown")


# Create FastAPI app
app = FastAPI(
    title="Monitoring Platform API",
    description="Production-grade microservices monitoring and alerting platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["auth"],
)
app.include_router(
    organizations.router,
    prefix="/api/v1/organizations",
    tags=["organizations"],
)
app.include_router(
    clients.router,
    prefix="/api/v1",
    tags=["clients"],
)
app.include_router(
    monitors.router,
    prefix="/api/v1/monitors",
    tags=["monitors"],
)
app.include_router(
    checks.router,
    prefix="/api/v1/checks",
    tags=["checks"],
)
app.include_router(
    alerts.router,
    prefix="/api/v1/alerts",
    tags=["alerts"],
)
app.include_router(
    alert_channels.router,
    prefix="/api/v1/alert-channels",
    tags=["alert-channels"],
)
app.include_router(
    incidents.router,
    prefix="/api/v1/incidents",
    tags=["incidents"],
)
app.include_router(
    status_pages.router,
    prefix="/api/v1/status-pages",
    tags=["status-pages"],
)
app.include_router(
    reports.router,
    prefix="/api/v1/reports",
    tags=["reports"],
)
app.include_router(
    status_pages.public_router,
    prefix="/api/v1/public/status-pages",
    tags=["public-status-pages"],
)
app.include_router(
    heartbeats.router,
    prefix="/api/v1/heartbeats",
    tags=["heartbeats"],
)
app.include_router(
    telegram_integration.router,
    prefix="/api/v1/integrations/telegram",
    tags=["integrations"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/v1/stats")
async def get_stats(
    db: DbSession,
    current_user: OptionalCurrentUser,
    organization_id: str | None = None,
) -> dict[str, int]:
    """Get aggregate stats for the dashboard."""
    internal_organization_id = None
    if organization_id is not None:
        import uuid

        try:
            public_organization_id = uuid.UUID(organization_id)
        except ValueError:
            public_organization_id = None
        organization = (
            await OrganizationService(db).get_organization(public_organization_id)
            if public_organization_id is not None
            else None
        )
        if (
            organization is None
            or current_user is None
            or not await OrganizationService(db).user_can_access(current_user, organization.id)
        ):
            return {
                "total_monitors": 0,
                "enabled_monitors": 0,
                "total_checks": 0,
                "failed_checks": 0,
                "active_alerts": 0,
                "total_heartbeats": 0,
            }
        internal_organization_id = organization.id

    monitor_stmt = select(Monitor)
    check_stmt = select(CheckResult)
    alert_stmt = select(Alert)
    if internal_organization_id is not None:
        monitor_stmt = monitor_stmt.where(Monitor.organization_id == internal_organization_id)
        check_stmt = check_stmt.where(CheckResult.organization_id == internal_organization_id)
        alert_stmt = alert_stmt.where(Alert.organization_id == internal_organization_id)

    total_monitors = (
        await db.execute(select(func.count()).select_from(monitor_stmt.subquery()))
    ).scalar() or 0
    enabled_monitors = (
        await db.execute(
            select(func.count()).select_from(
                monitor_stmt.where(Monitor.enabled.is_(True)).subquery(),
            )
        )
    ).scalar() or 0
    total_checks = (
        await db.execute(select(func.count()).select_from(check_stmt.subquery()))
    ).scalar() or 0
    failed_checks = (
        await db.execute(
            select(func.count()).select_from(
                check_stmt.where(CheckResult.success.is_(False)).subquery(),
            )
        )
    ).scalar() or 0
    active_alerts = (
        await db.execute(
            select(func.count()).select_from(
                alert_stmt.where(Alert.resolved.is_(False)).subquery(),
            )
        )
    ).scalar() or 0
    total_heartbeats = (
        await db.execute(
            select(func.count()).select_from(
                monitor_stmt.where(Monitor.monitor_type == "HEARTBEAT").subquery(),
            )
        )
    ).scalar() or 0

    return {
        "total_monitors": total_monitors,
        "enabled_monitors": enabled_monitors,
        "total_checks": total_checks,
        "failed_checks": failed_checks,
        "active_alerts": active_alerts,
        "total_heartbeats": total_heartbeats,
    }


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "message": "Monitoring Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
    }


import os  # noqa: E402

dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(dashboard_path):
    app.mount(
        "/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard"
    )
