from __future__ import annotations

import httpx
import structlog

from monitoring.alerting.base import AlertChannel, AlertPayload

logger = structlog.get_logger(__name__)


class SlackAlertChannel(AlertChannel):
    """Send alerts via Slack webhook."""

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def validate_config(self) -> bool:
        """Validate Slack configuration."""
        return bool(self.webhook_url)

    async def send(self, payload: AlertPayload) -> bool:
        """
        Send alert to Slack.

        Args:
            payload: Alert data to send

        Returns:
            True if successful, False otherwise
        """
        if not self.validate_config():
            logger.error("slack_invalid_config")
            return False

        # Determine emoji based on severity
        emoji_map = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":x:",
            "critical": ":rotating_light:",
        }
        emoji = emoji_map.get(payload.severity.lower(), ":bell:")

        # Determine color based on severity
        color_map = {
            "info": "#36a64f",
            "warning": "#ff9900",
            "error": "#ff0000",
            "critical": "#8b0000",
        }
        color = color_map.get(payload.severity.lower(), "#808080")

        slack_payload = {
            "text": f"{emoji} *{payload.title}*",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {
                            "title": "Monitor",
                            "value": payload.monitor_name,
                            "short": True,
                        },
                        {
                            "title": "Severity",
                            "value": payload.severity.upper(),
                            "short": True,
                        },
                        {
                            "title": "Message",
                            "value": payload.message,
                            "short": False,
                        },
                    ],
                    "footer": "Monitoring Platform",
                    "ts": payload.timestamp,
                }
            ],
        }

        if payload.monitor_url:
            slack_payload["attachments"][0]["fields"].append(
                {
                    "title": "Monitor URL",
                    "value": payload.monitor_url,
                    "short": False,
                }
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json=slack_payload,
                )

                response.raise_for_status()

                logger.info(
                    "slack_alert_sent",
                    webhook_url=self.webhook_url,
                    status_code=response.status_code,
                )
                return True

        except httpx.HTTPError as exc:
            logger.error(
                "slack_alert_failed",
                webhook_url=self.webhook_url,
                error=str(exc),
            )
            return False
