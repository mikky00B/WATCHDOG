from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.alerting.base import AlertChannel, AlertPayload
from monitoring.alerting.email import EmailAlertChannel
from monitoring.alerting.telegram import TelegramAlertChannel
from monitoring.config import Settings
from monitoring.models.incident import Incident
from monitoring.models.monitor import Monitor
from monitoring.models.notification import AlertEvent, NotificationChannel
from monitoring.schemas.notification import NotificationChannelCreate, NotificationChannelUpdate


class NotificationChannelService:
    """CRUD for organization notification channels."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_channel(self, data: NotificationChannelCreate) -> NotificationChannel:
        self._validate_channel_config(data.channel_type.value, data.config)
        channel = NotificationChannel(
            organization_id=data.organization_id,
            name=data.name,
            channel_type=data.channel_type.value,
            config=data.config,
            is_active=data.is_active,
        )
        self.db.add(channel)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def get_channel(self, channel_id: int) -> NotificationChannel | None:
        return await self.db.get(NotificationChannel, channel_id)

    async def list_channels(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: int | None = None,
        active_only: bool = False,
    ) -> tuple[list[NotificationChannel], int]:
        base_stmt = select(NotificationChannel)
        if organization_id is not None:
            base_stmt = base_stmt.where(NotificationChannel.organization_id == organization_id)
        if active_only:
            base_stmt = base_stmt.where(NotificationChannel.is_active.is_(True))

        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(NotificationChannel.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_channel(
        self,
        channel_id: int,
        data: NotificationChannelUpdate,
    ) -> NotificationChannel | None:
        channel = await self.get_channel(channel_id)
        if channel is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        if "config" in update_data and update_data["config"] is not None:
            self._validate_channel_config(channel.channel_type, update_data["config"])
        for key, value in update_data.items():
            setattr(channel, key, value)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def delete_channel(self, channel_id: int) -> bool:
        channel = await self.get_channel(channel_id)
        if channel is None:
            return False
        await self.db.delete(channel)
        return True

    def _validate_channel_config(self, channel_type: str, config: dict[str, object]) -> None:
        if channel_type == "EMAIL" and not config.get("email"):
            raise ValueError("EMAIL channel requires config.email")
        if channel_type == "TELEGRAM" and not config.get("chat_id"):
            raise ValueError("TELEGRAM channel requires config.chat_id")


class AlertEventService:
    """Queue alert events with cooldown suppression."""

    def __init__(self, db: AsyncSession, cooldown_minutes: int = 30):
        self.db = db
        self.cooldown_minutes = cooldown_minutes

    async def queue_for_incident(
        self,
        incident: Incident,
        event_type: str,
        message: str,
    ) -> list[AlertEvent]:
        channel_stmt = select(NotificationChannel).where(
            NotificationChannel.is_active.is_(True),
        )
        if incident.organization_id is None:
            channel_stmt = channel_stmt.where(NotificationChannel.organization_id.is_(None))
        else:
            channel_stmt = channel_stmt.where(
                NotificationChannel.organization_id == incident.organization_id
            )
        result = await self.db.execute(channel_stmt)

        events: list[AlertEvent] = []
        for channel in result.scalars().all():
            events.append(
                await self.queue_event(
                    organization_id=incident.organization_id,
                    monitor_id=incident.monitor_id,
                    incident_id=incident.id,
                    channel_id=channel.id,
                    event_type=event_type,
                    message=message,
                )
            )
        return events

    async def queue_event(
        self,
        organization_id: int | None,
        monitor_id: int | None,
        incident_id: int | None,
        channel_id: int | None,
        event_type: str,
        message: str,
    ) -> AlertEvent:
        status = "SUPPRESSED" if await self._inside_cooldown(
            monitor_id,
            incident_id,
            channel_id,
            event_type,
        ) else "PENDING"

        event = AlertEvent(
            organization_id=organization_id,
            monitor_id=monitor_id,
            incident_id=incident_id,
            channel_id=channel_id,
            event_type=event_type,
            status=status,
            message=message,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def mark_sent(self, event_id: int) -> AlertEvent | None:
        event = await self.db.get(AlertEvent, event_id)
        if event is None:
            return None
        event.status = "SENT"
        event.error_message = None
        event.sent_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def mark_failed(self, event_id: int, error_message: str) -> AlertEvent | None:
        event = await self.db.get(AlertEvent, event_id)
        if event is None:
            return None
        event.status = "FAILED"
        event.error_message = error_message
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def list_events(
        self,
        organization_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AlertEvent]:
        stmt = select(AlertEvent)
        if organization_id is not None:
            stmt = stmt.where(AlertEvent.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(AlertEvent.status == status)
        result = await self.db.execute(stmt.order_by(AlertEvent.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def _inside_cooldown(
        self,
        monitor_id: int | None,
        incident_id: int | None,
        channel_id: int | None,
        event_type: str,
    ) -> bool:
        window_start = datetime.now(UTC) - timedelta(minutes=self.cooldown_minutes)
        stmt = select(AlertEvent.id).where(
            AlertEvent.monitor_id == monitor_id,
            AlertEvent.incident_id == incident_id,
            AlertEvent.channel_id == channel_id,
            AlertEvent.event_type == event_type,
            AlertEvent.status.in_(["PENDING", "SENT"]),
            AlertEvent.created_at >= window_start,
        )
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None


EmailSenderFactory = Callable[[Settings, str], AlertChannel]


def create_email_sender(settings: Settings, recipient: str) -> EmailAlertChannel:
    return EmailAlertChannel(
        smtp_host=settings.smtp_host or "",
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user or "",
        smtp_password=settings.smtp_password or "",
        from_email=str(settings.from_email or settings.smtp_user or ""),
        to_emails=[recipient],
        use_tls=settings.smtp_use_tls,
        use_ssl=bool(settings.smtp_use_ssl),
        from_name=settings.from_name,
    )


class NotificationDeliveryService:
    """Deliver queued alert events through their configured notification channels."""

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        email_sender_factory: EmailSenderFactory = create_email_sender,
    ):
        self.db = db
        self.settings = settings
        self.email_sender_factory = email_sender_factory
        self.event_service = AlertEventService(db)

    async def process_pending(self, limit: int = 100) -> int:
        stmt = (
            select(AlertEvent)
            .where(AlertEvent.status == "PENDING")
            .order_by(AlertEvent.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)

        delivered = 0
        for event in result.scalars().all():
            if await self.deliver_event(event):
                delivered += 1
        return delivered

    async def deliver_event(self, event: AlertEvent) -> bool:
        channel = await self.db.get(NotificationChannel, event.channel_id)
        if channel is None:
            await self.event_service.mark_failed(event.id, "Notification channel not found")
            return False
        if not channel.is_active:
            await self.event_service.mark_failed(event.id, "Notification channel is inactive")
            return False
        try:
            if channel.channel_type == "EMAIL":
                return await self._deliver_email(event, channel)
            if channel.channel_type == "TELEGRAM":
                return await self._deliver_telegram(event, channel)
        except Exception as exc:
            await self.event_service.mark_failed(event.id, str(exc))
            return False

        await self.event_service.mark_failed(
            event.id,
            f"Unsupported notification channel type: {channel.channel_type}",
        )
        return False

    async def _deliver_email(self, event: AlertEvent, channel: NotificationChannel) -> bool:
        if not self.settings.email_enabled:
            await self.event_service.mark_failed(event.id, "Email delivery is disabled")
            return False
        recipient = channel.config.get("email")
        if not isinstance(recipient, str) or not recipient.strip():
            await self.event_service.mark_failed(event.id, "Email channel is missing config.email")
            return False

        sender = self.email_sender_factory(self.settings, recipient.strip())
        payload = await self._build_payload(event)
        if await sender.send(payload):
            await self.event_service.mark_sent(event.id)
            return True

        await self.event_service.mark_failed(
            event.id,
            getattr(sender, "last_error", None) or "Email sender returned failure",
        )
        return False

    async def _deliver_telegram(self, event: AlertEvent, channel: NotificationChannel) -> bool:
        if not self.settings.telegram_bot_token:
            await self.event_service.mark_failed(event.id, "Telegram bot token is not configured")
            return False
        chat_id = channel.config.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            await self.event_service.mark_failed(
                event.id,
                "Telegram channel is missing config.chat_id",
            )
            return False

        sender = TelegramAlertChannel(
            token=self.settings.telegram_bot_token,
            allowed_chat_ids=[chat_id.strip()],
        )
        payload = await self._build_payload(event)
        if await sender.send(payload):
            await self.event_service.mark_sent(event.id)
            return True

        await self.event_service.mark_failed(event.id, "Telegram sender returned failure")
        return False

    async def _build_payload(self, event: AlertEvent) -> AlertPayload:
        monitor = await self.db.get(Monitor, event.monitor_id) if event.monitor_id else None
        incident = await self.db.get(Incident, event.incident_id) if event.incident_id else None

        title = (
            incident.title if incident is not None else event.event_type.replace("_", " ").title()
        )
        severity = incident.severity.lower() if incident is not None else "info"
        timestamp = (
            event.created_at.isoformat() if event.created_at else datetime.now(UTC).isoformat()
        )

        return AlertPayload(
            alert_id=event.id,
            monitor_name=monitor.name if monitor is not None else "Unknown monitor",
            severity=severity,
            title=title,
            message=event.message,
            timestamp=timestamp,
            monitor_url=monitor.url if monitor is not None else None,
        )
