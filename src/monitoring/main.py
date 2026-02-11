from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from monitoring.api.v1 import alerts, checks, heartbeats, monitors
from monitoring.config import get_settings
from monitoring.database import AsyncSessionLocal, close_db, init_db
from monitoring.models.alert import Alert
from monitoring.models.check_result import CheckResult
from monitoring.models.heartbeat import Heartbeat
from monitoring.models.monitor import Monitor
from monitoring.utils.logging import get_logger, setup_logging

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

    # Initialize database (development only - use Alembic in production)
    await init_db()

    yield

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
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
    heartbeats.router,
    prefix="/api/v1/heartbeats",
    tags=["heartbeats"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/v1/stats")
async def get_stats() -> dict[str, int]:
    """Get aggregate stats for the dashboard."""
    async with AsyncSessionLocal() as db:
        total_monitors = (await db.execute(select(func.count(Monitor.id)))).scalar() or 0
        enabled_monitors = (
            await db.execute(
                select(func.count(Monitor.id)).where(Monitor.enabled == True)  # noqa: E712
            )
        ).scalar() or 0
        total_checks = (await db.execute(select(func.count(CheckResult.id)))).scalar() or 0
        failed_checks = (
            await db.execute(
                select(func.count(CheckResult.id)).where(CheckResult.success == False)  # noqa: E712
            )
        ).scalar() or 0
        active_alerts = (
            await db.execute(
                select(func.count(Alert.id)).where(Alert.resolved == False)  # noqa: E712
            )
        ).scalar() or 0
        total_heartbeats = (
            await db.execute(select(func.count(Heartbeat.id)))
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


# Mount static files for dashboard (must be last)
import os  # noqa: E402

dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard")
