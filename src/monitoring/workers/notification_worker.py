from __future__ import annotations

import asyncio

import structlog

from monitoring.config import Settings, get_settings
from monitoring.database import AsyncSessionLocal
from monitoring.services.notification_service import NotificationDeliveryService

logger = structlog.get_logger(__name__)


class NotificationWorker:
    """Worker for delivering queued alert events through notification channels."""

    def __init__(
        self,
        settings: Settings | None = None,
        batch_size: int = 100,
        check_interval_seconds: int = 5,
    ):
        self.settings = settings or get_settings()
        self.batch_size = batch_size
        self.check_interval_seconds = check_interval_seconds
        self.running = False

    async def start(self) -> None:
        self.running = True
        logger.info(
            "notification_worker_started",
            batch_size=self.batch_size,
            check_interval=self.check_interval_seconds,
        )

        while self.running:
            try:
                await self._process_pending_events()
                await asyncio.sleep(self.check_interval_seconds)
            except Exception as exc:
                logger.error("notification_worker_error", error=str(exc), exc_info=True)
                await asyncio.sleep(self.check_interval_seconds)

    async def stop(self) -> None:
        self.running = False
        logger.info("notification_worker_stopped")

    async def _process_pending_events(self) -> int:
        async with AsyncSessionLocal() as db:
            delivered = await NotificationDeliveryService(
                db,
                self.settings,
            ).process_pending(limit=self.batch_size)
            await db.commit()
            if delivered:
                logger.info("notification_events_delivered", count=delivered)
            return delivered
