"""Telegram service for webhook update handling and command execution."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.config import get_settings
from monitoring.schemas.monitor import MonitorUpdate
from monitoring.schemas.telegram import TelegramCallbackQuery, TelegramMessage, TelegramUpdate
from monitoring.services.alert_service import AlertService
from monitoring.services.monitor_service import MonitorService

logger = structlog.get_logger(__name__)

WEBHOOK_URL = (
    "https://mathilda-repletive-detractingly.ngrok-free.dev/"
    "api/v1/integrations/telegram/webhook"
)


class TelegramService:
    """Handle Telegram commands and callback queries."""

    def __init__(
        self,
        db: AsyncSession,
        bot_token: str,
        allowed_chat_ids: list[str],
    ):
        self.db = db
        self.bot_token = bot_token
        self.allowed_chat_ids = {str(chat_id).strip() for chat_id in allowed_chat_ids}
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.monitor_service = MonitorService(db)
        self.alert_service = AlertService(db)

    async def handle_update(self, update: TelegramUpdate) -> None:
        """Route Telegram updates to message or callback handlers."""
        if update.callback_query is not None:
            await self._handle_callback_query(update.callback_query)
            return

        if update.message is not None:
            await self._handle_message(update.message)

    async def _handle_message(self, message: TelegramMessage) -> None:
        chat_id = str(message.chat.id)
        if not self._is_authorized(chat_id):
            logger.warning("telegram_unauthorized_access", chat_id=chat_id)
            return

        if not message.text:
            return

        parts = message.text.strip().split()
        if not parts:
            return

        command = parts[0].lower()
        args = parts[1:]

        logger.info("telegram_command_received", chat_id=chat_id, command=command)

        if command == "/status":
            await self._handle_status(chat_id)
        elif command == "/monitors":
            await self._handle_monitors(chat_id)
        elif command == "/alerts":
            await self._handle_alerts(chat_id)
        elif command == "/ack":
            await self._handle_ack(chat_id, args)
        elif command == "/resolve":
            await self._handle_resolve(chat_id, args)
        elif command == "/enable":
            await self._handle_enable(chat_id, args)
        elif command == "/disable":
            await self._handle_disable(chat_id, args)
        else:
            await self._send_message(chat_id, self._usage_text())

    async def _handle_callback_query(self, callback: TelegramCallbackQuery) -> None:
        if callback.message is None:
            return

        chat_id = str(callback.message.chat.id)
        if not self._is_authorized(chat_id):
            logger.warning("telegram_unauthorized_callback", chat_id=chat_id)
            return

        if not callback.data or ":" not in callback.data:
            if callback.id:
                await self._answer_callback_query(callback.id, "Invalid action")
            return

        action, raw_id = callback.data.split(":", 1)
        message_id = callback.message.message_id

        logger.info("telegram_callback_received", chat_id=chat_id, action=action)

        if action == "ack":
            result = await self._execute_ack(raw_id)
            await self._finalize_callback(callback.id, chat_id, message_id, result)
            return

        if action == "resolve":
            result = await self._execute_resolve(raw_id)
            await self._finalize_callback(callback.id, chat_id, message_id, result)
            return

        if callback.id:
            await self._answer_callback_query(callback.id, "Invalid action")

    async def _finalize_callback(
        self,
        callback_id: str | None,
        chat_id: str,
        message_id: int | None,
        result: tuple[bool, str],
    ) -> None:
        ok, text_message = result
        if message_id is not None:
            await self._edit_message(chat_id, message_id, text_message)
        else:
            await self._send_message(chat_id, text_message)

        if callback_id:
            await self._answer_callback_query(callback_id, "Done" if ok else text_message)

    async def _handle_status(self, chat_id: str) -> None:
        monitors, total_monitors = await self.monitor_service.list_monitors(limit=10000)
        _, enabled_monitors = await self.monitor_service.list_monitors(
            enabled_only=True,
            limit=10000,
        )
        _, active_alerts = await self.alert_service.list_alerts(
            unresolved_only=True,
            limit=10000,
        )

        failed_checks_24h = await self._failed_checks_last_24h()

        status_message = (
            "*WATCHDOG Status*\n"
            f"Total monitors: {total_monitors}\n"
            f"Enabled monitors: {enabled_monitors}\n"
            f"Active alerts: {active_alerts}\n"
            f"Failed checks (24h): {failed_checks_24h}"
        )
        if not monitors:
            status_message += "\nNo monitors configured."

        await self._send_message(chat_id, status_message)

    async def _handle_monitors(self, chat_id: str) -> None:
        monitors, _ = await self.monitor_service.list_monitors(limit=100)
        if not monitors:
            await self._send_message(chat_id, "No monitors found")
            return

        latest_status = await self._latest_monitor_status()

        lines = ["*Monitors*"]
        for monitor in monitors:
            success = latest_status.get(monitor.id)
            state = "UNKNOWN"
            if success is True:
                state = "UP"
            elif success is False:
                state = "DOWN"
            enabled = "Enabled" if monitor.enabled else "Disabled"
            lines.append(f"- {monitor.id}: {monitor.name} [{state}] ({enabled})")

        await self._send_message(chat_id, "\n".join(lines))

    async def _handle_alerts(self, chat_id: str) -> None:
        alerts, _ = await self.alert_service.list_alerts(
            unresolved_only=True,
            limit=20,
        )
        if not alerts:
            await self._send_message(chat_id, "No unresolved alerts")
            return

        lines = ["*Unresolved Alerts*"]
        for alert in alerts:
            lines.append(f"- {alert.id}: {alert.title} ({alert.severity})")
        await self._send_message(chat_id, "\n".join(lines))

    async def _handle_ack(self, chat_id: str, args: list[str]) -> None:
        if len(args) != 1:
            await self._send_message(chat_id, "Usage: /ack <alert_id>")
            return
        _, reply_text = await self._execute_ack(args[0])
        await self._send_message(chat_id, reply_text)

    async def _handle_resolve(self, chat_id: str, args: list[str]) -> None:
        if len(args) != 1:
            await self._send_message(chat_id, "Usage: /resolve <alert_id>")
            return
        _, reply_text = await self._execute_resolve(args[0])
        await self._send_message(chat_id, reply_text)

    async def _handle_enable(self, chat_id: str, args: list[str]) -> None:
        if len(args) != 1:
            await self._send_message(chat_id, "Usage: /enable <monitor_id>")
            return

        monitor_id = self._parse_positive_int(args[0])
        if monitor_id is None:
            await self._send_message(chat_id, "Invalid ID")
            return

        monitor = await self.monitor_service.get_monitor_by_internal_id(monitor_id)
        if monitor is None:
            await self._send_message(chat_id, f"Monitor {monitor_id} not found")
            return

        await self.monitor_service.update_monitor(
            monitor.public_id,
            MonitorUpdate(enabled=True),
        )
        await self._send_message(chat_id, f"Monitor {monitor_id} enabled")

    async def _handle_disable(self, chat_id: str, args: list[str]) -> None:
        if len(args) != 1:
            await self._send_message(chat_id, "Usage: /disable <monitor_id>")
            return

        monitor_id = self._parse_positive_int(args[0])
        if monitor_id is None:
            await self._send_message(chat_id, "Invalid ID")
            return

        monitor = await self.monitor_service.get_monitor_by_internal_id(monitor_id)
        if monitor is None:
            await self._send_message(chat_id, f"Monitor {monitor_id} not found")
            return

        await self.monitor_service.update_monitor(
            monitor.public_id,
            MonitorUpdate(enabled=False),
        )
        await self._send_message(chat_id, f"Monitor {monitor_id} disabled")

    async def _execute_ack(self, raw_id: str) -> tuple[bool, str]:
        alert_id = self._parse_positive_int(raw_id)
        if alert_id is None:
            return False, "Invalid ID"

        alert = await self.alert_service.acknowledge_alert(alert_id)
        if alert is None:
            return False, f"Alert {alert_id} not found"

        return True, f"Alert {alert_id} acknowledged"

    async def _execute_resolve(self, raw_id: str) -> tuple[bool, str]:
        alert_id = self._parse_positive_int(raw_id)
        if alert_id is None:
            return False, "Invalid ID"

        alert = await self.alert_service.resolve_alert(alert_id)
        if alert is None:
            return False, f"Alert {alert_id} not found"

        return True, f"Alert {alert_id} resolved"

    async def _failed_checks_last_24h(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM check_results
                WHERE success = false AND checked_at >= :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
        return int(result.scalar() or 0)

    async def _latest_monitor_status(self) -> dict[int, bool]:
        result = await self.db.execute(
            text(
                """
                SELECT c.monitor_id, c.success
                FROM check_results c
                JOIN (
                    SELECT monitor_id, MAX(checked_at) AS max_checked_at
                    FROM check_results
                    GROUP BY monitor_id
                ) latest
                    ON latest.monitor_id = c.monitor_id
                   AND latest.max_checked_at = c.checked_at
                """
            )
        )
        return {int(row.monitor_id): bool(row.success) for row in result}

    async def _send_message(
        self,
        chat_id: str,
        text_message: str,
        reply_markup: dict | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text_message,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.api_url}/sendMessage", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("telegram_send_message_failed", error=str(exc), chat_id=chat_id)

    async def _edit_message(
        self,
        chat_id: str,
        message_id: int,
        text_message: str,
        reply_markup: dict | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text_message,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/editMessageText",
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "telegram_edit_message_failed",
                error=str(exc),
                chat_id=chat_id,
                message_id=message_id,
            )

    async def _answer_callback_query(
        self,
        callback_query_id: str,
        text_message: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text_message:
            payload["text"] = text_message

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/answerCallbackQuery",
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "telegram_answer_callback_failed",
                error=str(exc),
                callback_query_id=callback_query_id,
            )

    def _is_authorized(self, chat_id: str) -> bool:
        return chat_id in self.allowed_chat_ids

    @staticmethod
    def _parse_positive_int(raw_value: str) -> int | None:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return value

    @staticmethod
    def _usage_text() -> str:
        return (
            "Supported commands:\n"
            "/status\n"
            "/monitors\n"
            "/alerts\n"
            "/ack <alert_id>\n"
            "/resolve <alert_id>\n"
            "/enable <monitor_id>\n"
            "/disable <monitor_id>"
        )


async def register_webhook() -> bool:
    """Register Telegram webhook manually."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("telegram_webhook_registration_skipped", reason="missing_bot_token")
        return False
    if not settings.telegram_webhook_secret:
        logger.warning(
            "telegram_webhook_registration_skipped",
            reason="missing_webhook_secret",
        )
        return False

    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    payload = {
        "url": WEBHOOK_URL,
        "secret_token": settings.telegram_webhook_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
            data = response.json()
            ok = bool(data.get("ok"))
            if ok:
                logger.info("telegram_webhook_registered", webhook_url=WEBHOOK_URL)
            else:
                logger.error(
                    "telegram_webhook_registration_failed",
                    description=data.get("description"),
                )
            return ok
    except httpx.HTTPError as exc:
        logger.error("telegram_webhook_registration_error", error=str(exc))
        return False
