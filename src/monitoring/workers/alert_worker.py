from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from monitoring.alerting.base import AlertChannel, AlertPayload
from monitoring.alerting.telegram import TelegramAlertChannel
from monitoring.config import get_settings
from monitoring.database import AsyncSessionLocal
from monitoring.models.alert import Alert
from monitoring.services.alert_service import AlertService

settings = get_settings()


logger = structlog.get_logger(__name__)


class AlertWorker:
    """Worker for delivering alerts through configured channels with retry logic."""

    def __init__(
        self,
        channels: list[AlertChannel],
        batch_size: int = 100,
        check_interval_seconds: int = 5,
        max_retries: int = 3,
        retry_delay_seconds: int = 60,
    ):
        self.channels = list(channels)
        if settings.telegram_bot_token and settings.telegram_allowed_chat_ids:
            self.channels.append(
                TelegramAlertChannel(
                    token=settings.telegram_bot_token,
                    allowed_chat_ids=settings.telegram_allowed_chat_ids,
                )
            )
        self.batch_size = batch_size
        self.check_interval_seconds = check_interval_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.running = False

        # Track delivery attempts: alert_id -> (attempt_count, last_attempt_time)
        self._delivery_attempts: Dict[int, tuple[int, datetime]] = {}

    async def start(self) -> None:
        """Start the alert worker."""
        self.running = True
        logger.info(
            "alert_worker_started",
            channel_count=len(self.channels),
            batch_size=self.batch_size,
            check_interval=self.check_interval_seconds,
        )

        while self.running:
            try:
                await self._process_pending_alerts()
                await asyncio.sleep(self.check_interval_seconds)
            except Exception as exc:
                logger.error("alert_worker_error", error=str(exc), exc_info=True)
                await asyncio.sleep(self.check_interval_seconds)

    async def stop(self) -> None:
        """Stop the alert worker."""
        self.running = False
        logger.info("alert_worker_stopped")

    def _should_retry_alert(self, alert_id: int) -> bool:
        """
        Check if an alert should be retried based on attempt history.

        Args:
            alert_id: Alert ID to check

        Returns:
            True if alert should be retried, False otherwise
        """
        if alert_id not in self._delivery_attempts:
            return True

        attempt_count, last_attempt = self._delivery_attempts[alert_id]

        # Max retries exceeded
        if attempt_count >= self.max_retries:
            logger.warning(
                "alert_max_retries_exceeded",
                alert_id=alert_id,
                attempts=attempt_count,
            )
            return False

        # Check if enough time has passed since last attempt
        time_since_last = datetime.now(timezone.utc) - last_attempt
        if time_since_last.total_seconds() < self.retry_delay_seconds:
            return False

        return True

    def _record_delivery_attempt(self, alert_id: int) -> None:
        """Record a delivery attempt for an alert."""
        if alert_id in self._delivery_attempts:
            attempt_count, _ = self._delivery_attempts[alert_id]
            self._delivery_attempts[alert_id] = (
                attempt_count + 1,
                datetime.now(timezone.utc),
            )
        else:
            self._delivery_attempts[alert_id] = (1, datetime.now(timezone.utc))

    def _clear_delivery_attempt(self, alert_id: int) -> None:
        """Clear delivery attempt tracking for an alert."""
        if alert_id in self._delivery_attempts:
            del self._delivery_attempts[alert_id]

    async def _process_pending_alerts(self) -> None:
        """Process pending alerts and deliver them."""
        async with AsyncSessionLocal() as db:
            # Eagerly load monitor relationship to avoid lazy-load in async context
            stmt = (
                select(Alert)
                .options(joinedload(Alert.monitor))
                .where(Alert.resolved == False)  # noqa: E712
                .where(
                    Alert.acknowledged == False
                )  # noqa: E712 - Don't re-send acknowledged alerts
                .order_by(Alert.triggered_at.asc())  # Oldest first
                .limit(self.batch_size)
            )
            result = await db.execute(stmt)
            alerts = list(result.scalars().unique().all())

            if alerts:
                logger.info(
                    "processing_alerts",
                    alert_count=len(alerts),
                )

                # Process alerts concurrently
                tasks = []
                for alert in alerts:
                    if self._should_retry_alert(alert.id):
                        tasks.append(self._deliver_alert(alert))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            # Clean up old delivery attempts (older than 1 hour)
            self._cleanup_old_attempts()

    def _cleanup_old_attempts(self) -> None:
        """Remove tracking for old delivery attempts."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        to_remove = [
            alert_id
            for alert_id, (_, last_attempt) in self._delivery_attempts.items()
            if last_attempt < cutoff
        ]
        for alert_id in to_remove:
            del self._delivery_attempts[alert_id]

    async def _deliver_alert(self, alert: Alert) -> None:
        """
        Deliver alert through all configured channels.

        Args:
            alert: Alert to deliver
        """
        self._record_delivery_attempt(alert.id)

        any_channel_succeeded = False
        failed_channels = []

        for channel in self.channels:
            try:
                payload = AlertPayload(
                    alert_id=alert.id,
                    monitor_name=alert.monitor.name if alert.monitor else "Unknown",
                    severity=alert.severity,
                    title=alert.title,
                    message=alert.message,
                    timestamp=alert.triggered_at.isoformat(),
                    monitor_url=getattr(alert.monitor, "url", None)
                    if alert.monitor
                    else None,
                )
                send_ok = await channel.send(payload)
                if send_ok:
                    logger.info(
                        "alert_delivered",
                        alert_id=alert.id,
                        channel=channel.__class__.__name__,
                        monitor_name=alert.monitor.name if alert.monitor else "Unknown",
                    )
                    any_channel_succeeded = True
                else:
                    failed_channels.append(channel.__class__.__name__)
                    logger.warning(
                        "alert_delivery_channel_returned_false",
                        alert_id=alert.id,
                        channel=channel.__class__.__name__,
                    )

            except Exception as exc:
                failed_channels.append(channel.__class__.__name__)
                logger.error(
                    "alert_delivery_error",
                    alert_id=alert.id,
                    channel=channel.__class__.__name__,
                    error=str(exc),
                    exc_info=True,
                )

        if any_channel_succeeded:
            async with AsyncSessionLocal() as db:
                try:
                    alert_service = AlertService(db)
                    await alert_service.acknowledge_alert(alert.id)
                    await db.commit()
                    self._clear_delivery_attempt(alert.id)
                    logger.info("alert_acknowledged", alert_id=alert.id)
                except Exception as exc:
                    logger.error(
                        "alert_acknowledgement_failed",
                        alert_id=alert.id,
                        error=str(exc),
                        exc_info=True,
                    )
        else:
            attempt_count, _ = self._delivery_attempts.get(alert.id, (0, None))
            logger.error(
                "alert_delivery_all_channels_failed",
                alert_id=alert.id,
                attempt=attempt_count,
                max_retries=self.max_retries,
                failed_channels=failed_channels,
            )

    async def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "running": self.running,
            "channels": len(self.channels),
            "pending_retries": len(self._delivery_attempts),
            "retry_details": [
                {
                    "alert_id": alert_id,
                    "attempts": attempts,
                    "last_attempt": last_attempt.isoformat(),
                }
                for alert_id, (
                    attempts,
                    last_attempt,
                ) in self._delivery_attempts.items()
            ],
        }
