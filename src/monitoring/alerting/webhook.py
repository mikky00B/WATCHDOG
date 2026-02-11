from __future__ import annotations

import httpx
import structlog

from monitoring.alerting.base import AlertChannel, AlertPayload

logger = structlog.get_logger(__name__)


class WebhookAlertChannel(AlertChannel):
    """Send alerts via HTTP webhook."""

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def validate_config(self) -> bool:
        """Validate webhook configuration."""
        return bool(self.webhook_url)

    async def send(self, payload: AlertPayload) -> bool:
        """
        Send alert to webhook.

        Args:
            payload: Alert data to send

        Returns:
            True if successful, False otherwise
        """
        if not self.validate_config():
            logger.error("webhook_invalid_config")
            return False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "monitor_name": payload.monitor_name,
                        "severity": payload.severity,
                        "title": payload.title,
                        "message": payload.message,
                        "timestamp": payload.timestamp,
                        "monitor_url": payload.monitor_url,
                    },
                )

                response.raise_for_status()

                logger.info(
                    "webhook_alert_sent",
                    webhook_url=self.webhook_url,
                    status_code=response.status_code,
                )
                return True

        except httpx.HTTPError as exc:
            logger.error(
                "webhook_alert_failed",
                webhook_url=self.webhook_url,
                error=str(exc),
            )
            return False
