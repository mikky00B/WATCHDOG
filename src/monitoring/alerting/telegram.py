"""Telegram alert channel."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from monitoring.alerting.base import AlertChannel, AlertPayload
from monitoring.utils.exceptions import AlertDeliveryError

logger = structlog.get_logger(__name__)


@dataclass
class _DeliveryFailure:
    chat_id: str
    reason: str


class TelegramAlertChannel(AlertChannel):
    """Send alerts to Telegram chats using Bot API."""

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list[str],
        timeout_seconds: float = 10.0,
    ):
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids
        self.timeout_seconds = timeout_seconds
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def validate_config(self) -> bool:
        """Validate Telegram channel configuration."""
        return bool(self.token and self.allowed_chat_ids)

    async def send(self, payload: AlertPayload) -> bool:
        """Send alert message to all configured chats."""
        if not self.validate_config():
            logger.warning("telegram_channel_not_configured")
            return False

        text = self._format_alert(payload)
        keyboard = self._build_inline_keyboard(payload.alert_id)
        failures: list[_DeliveryFailure] = []
        delivered_count = 0

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for chat_id in self.allowed_chat_ids:
                try:
                    await self._send_message(client, chat_id, text, keyboard)
                    delivered_count += 1
                except httpx.HTTPStatusError as exc:
                    reason = (
                        f"http_status={exc.response.status_code}"
                        if exc.response is not None
                        else "http_status_error"
                    )
                    failures.append(_DeliveryFailure(chat_id=chat_id, reason=reason))
                    logger.error(
                        "telegram_delivery_http_error",
                        chat_id=chat_id,
                        status_code=exc.response.status_code if exc.response else None,
                    )
                except httpx.RequestError as exc:
                    failures.append(_DeliveryFailure(chat_id=chat_id, reason=str(exc)))
                    logger.error(
                        "telegram_delivery_network_error",
                        chat_id=chat_id,
                        error=str(exc),
                    )

        if delivered_count == 0:
            failure_summary = ", ".join(
                f"{failure.chat_id}:{failure.reason}" for failure in failures
            )
            raise AlertDeliveryError(
                alert_id=payload.alert_id,
                channel="TelegramAlertChannel",
                reason=failure_summary or "no_recipients_delivered",
            )

        logger.info(
            "telegram_alert_delivered",
            alert_id=payload.alert_id,
            delivered_count=delivered_count,
            failed_count=len(failures),
        )
        return True

    def _format_alert(self, payload: AlertPayload) -> str:
        header = "\U0001f6a8 *WATCHDOG ALERT*"
        return (
            f"{header}\n"
            f"Monitor: {payload.monitor_name}\n"
            f"Severity: {payload.severity}\n"
            f"Triggered: {payload.timestamp}\n"
            f"Message:\n"
            f"{payload.message}"
        )

    def _build_inline_keyboard(
        self, alert_id: int
    ) -> dict[str, list[list[dict[str, str]]]] | None:
        if alert_id <= 0:
            return None
        return {
            "inline_keyboard": [
                [
                    {"text": "Acknowledge", "callback_data": f"ack:{alert_id}"},
                    {"text": "Resolve", "callback_data": f"resolve:{alert_id}"},
                ]
            ]
        }

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        chat_id: str,
        text: str,
        reply_markup: dict[str, list[list[dict[str, str]]]] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        response = await client.post(f"{self.api_url}/sendMessage", json=payload)
        response.raise_for_status()
