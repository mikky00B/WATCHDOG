#!/usr/bin/env python3
"""Seed database with sample data for development."""
from __future__ import annotations

import asyncio

from monitoring.database import AsyncSessionLocal
from monitoring.models.monitor import Monitor
from monitoring.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


async def seed_database() -> None:
    """Seed database with sample monitors."""
    async with AsyncSessionLocal() as db:
        try:
            # Create sample monitors
            monitors = [
                Monitor(
                    name="Example API",
                    url="https://api.example.com/health",
                    interval_seconds=60,
                    timeout_seconds=5.0,
                    enabled=True,
                ),
                Monitor(
                    name="Google",
                    url="https://www.google.com",
                    interval_seconds=300,
                    timeout_seconds=10.0,
                    enabled=True,
                ),
                Monitor(
                    name="GitHub API",
                    url="https://api.github.com",
                    interval_seconds=120,
                    timeout_seconds=5.0,
                    enabled=True,
                ),
            ]

            for monitor in monitors:
                db.add(monitor)

            await db.commit()

            logger.info(
                "database_seeded",
                monitor_count=len(monitors),
            )

        except Exception as exc:
            logger.error("seed_failed", error=str(exc))
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())
