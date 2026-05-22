from __future__ import annotations

from datetime import UTC, datetime

import pytest
from monitoring.config import Settings
from monitoring.models.incident import Incident
from monitoring.models.notification import AlertEvent, NotificationChannel
from monitoring.models.organization import Organization
from monitoring.models.user import User
from monitoring.schemas.notification import NotificationChannelCreate, NotificationChannelType
from monitoring.services.notification_service import (
    AlertEventService,
    NotificationChannelService,
    NotificationDeliveryService,
    create_email_sender,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
async def test_create_email_channel_validates_config(test_db: AsyncSession) -> None:
    service = NotificationChannelService(test_db)

    with pytest.raises(ValueError):
        await service.create_channel(
            NotificationChannelCreate(
                name="Email",
                channel_type=NotificationChannelType.EMAIL,
                config={},
            )
        )

    channel = await service.create_channel(
        NotificationChannelCreate(
            name="Email",
            channel_type=NotificationChannelType.EMAIL,
            config={"email": "alerts@example.com"},
        )
    )

    assert channel.id is not None
    assert channel.channel_type == "EMAIL"


@pytest.mark.unit
async def test_alert_event_cooldown_suppresses_duplicate(
    test_db: AsyncSession,
    sample_monitor,
) -> None:
    user = User(
        full_name="Owner",
        email="owner@example.com",
        password_hash="hash",
    )
    test_db.add(user)
    await test_db.flush()

    channel = NotificationChannel(
        organization_id=None,
        name="Email",
        channel_type="EMAIL",
        config={"email": "alerts@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    incident = Incident(
        monitor_id=sample_monitor.id,
        title="API down",
        reason="HTTP 500",
        started_at=datetime.now(UTC),
    )
    test_db.add(incident)
    await test_db.flush()

    service = AlertEventService(test_db, cooldown_minutes=30)
    first = await service.queue_event(
        organization_id=None,
        monitor_id=sample_monitor.id,
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="MONITOR_DOWN",
        message="HTTP 500",
    )
    second = await service.queue_event(
        organization_id=None,
        monitor_id=sample_monitor.id,
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="MONITOR_DOWN",
        message="HTTP 500 again",
    )

    assert first.status == "PENDING"
    assert second.status == "SUPPRESSED"


@pytest.mark.unit
async def test_unscoped_incident_only_queues_unscoped_channels(
    test_db: AsyncSession,
    sample_monitor,
) -> None:
    user = User(
        full_name="Owner",
        email="scoped-owner@example.com",
        password_hash="hash",
    )
    test_db.add(user)
    await test_db.flush()

    org = Organization(name="Acme", slug="acme", owner_id=user.id)
    test_db.add(org)
    await test_db.flush()

    unscoped_channel = NotificationChannel(
        organization_id=None,
        name="Legacy email",
        channel_type="EMAIL",
        config={"email": "legacy@example.com"},
    )
    scoped_channel = NotificationChannel(
        organization_id=org.id,
        name="Scoped email",
        channel_type="EMAIL",
        config={"email": "scoped@example.com"},
    )
    test_db.add_all([unscoped_channel, scoped_channel])
    await test_db.flush()

    incident = Incident(
        monitor_id=sample_monitor.id,
        title="Legacy monitor down",
        reason="HTTP 500",
        started_at=datetime.now(UTC),
    )
    test_db.add(incident)
    await test_db.flush()

    events = await AlertEventService(test_db).queue_for_incident(
        incident=incident,
        event_type="MONITOR_DOWN",
        message="HTTP 500",
    )

    result = await test_db.execute(select(AlertEvent).order_by(AlertEvent.id))
    persisted_events = list(result.scalars().all())

    assert [event.channel_id for event in events] == [unscoped_channel.id]
    assert [event.channel_id for event in persisted_events] == [unscoped_channel.id]


@pytest.mark.unit
async def test_delivery_sends_email_to_alert_channel_recipient(
    test_db: AsyncSession,
    sample_monitor,
) -> None:
    sent: list[dict[str, object]] = []

    class FakeEmailSender:
        def __init__(self, recipient: str):
            self.recipient = recipient
            self.last_error = None

        async def send(self, payload) -> bool:
            sent.append({"recipient": self.recipient, "payload": payload})
            return True

    def sender_factory(settings: Settings, recipient: str) -> FakeEmailSender:
        assert settings.smtp_host == "smtp.titan.email"
        return FakeEmailSender(recipient)

    channel = NotificationChannel(
        organization_id=None,
        name="Client email",
        channel_type="EMAIL",
        config={"email": "client@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    incident = Incident(
        monitor_id=sample_monitor.id,
        title="API down",
        reason="HTTP 500",
        severity="HIGH",
        started_at=datetime.now(UTC),
    )
    test_db.add(incident)
    await test_db.flush()

    event = await AlertEventService(test_db).queue_event(
        organization_id=None,
        monitor_id=sample_monitor.id,
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="MONITOR_DOWN",
        message="HTTP 500",
    )

    delivered = await NotificationDeliveryService(
        test_db,
        Settings(
            email_enabled=True,
            smtp_host="smtp.titan.email",
            smtp_port=587,
            smtp_user="michael@clevermike.studio",
            smtp_password="password",
        ),
        email_sender_factory=sender_factory,
    ).process_pending()

    await test_db.refresh(event)

    assert delivered == 1
    assert event.status == "SENT"
    assert event.sent_at is not None
    assert sent[0]["recipient"] == "client@example.com"
    assert sent[0]["payload"].monitor_name == sample_monitor.name


@pytest.mark.unit
async def test_delivery_fails_when_email_channel_has_no_recipient(
    test_db: AsyncSession,
) -> None:
    channel = NotificationChannel(
        organization_id=None,
        name="Broken email",
        channel_type="EMAIL",
        config={"email": ""},
    )
    test_db.add(channel)
    await test_db.flush()

    event = await AlertEventService(test_db).queue_event(
        organization_id=None,
        monitor_id=None,
        incident_id=None,
        channel_id=channel.id,
        event_type="TEST",
        message="Test alert",
    )

    delivered = await NotificationDeliveryService(
        test_db,
        Settings(
            email_enabled=True,
            smtp_host="smtp.titan.email",
            smtp_port=587,
            smtp_user="michael@clevermike.studio",
            smtp_password="password",
        ),
    ).process_pending()

    await test_db.refresh(event)

    assert delivered == 0
    assert event.status == "FAILED"
    assert event.error_message == "Email channel is missing config.email"


@pytest.mark.unit
def test_create_email_sender_uses_implicit_ssl_for_port_465() -> None:
    sender = create_email_sender(
        Settings(
            email_enabled=True,
            smtp_host="smtp.titan.email",
            smtp_port=465,
            smtp_user="michael@clevermike.studio",
            smtp_password="password",
        ),
        "recipient@example.com",
    )

    assert sender.use_ssl is True
    assert sender.use_tls is True
    assert sender.to_emails == ["recipient@example.com"]
    assert sender.from_email == "michael@clevermike.studio"


@pytest.mark.unit
async def test_delivery_records_email_sender_error(
    test_db: AsyncSession,
) -> None:
    class FailingEmailSender:
        last_error = "SMTP authentication failed (535): invalid credentials"

        async def send(self, payload) -> bool:
            return False

    def sender_factory(settings: Settings, recipient: str) -> FailingEmailSender:
        return FailingEmailSender()

    channel = NotificationChannel(
        organization_id=None,
        name="Client email",
        channel_type="EMAIL",
        config={"email": "client@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    event = await AlertEventService(test_db).queue_event(
        organization_id=None,
        monitor_id=None,
        incident_id=None,
        channel_id=channel.id,
        event_type="TEST",
        message="Test alert",
    )

    delivered = await NotificationDeliveryService(
        test_db,
        Settings(
            email_enabled=True,
            smtp_host="smtp.titan.email",
            smtp_port=465,
            smtp_user="michael@clevermike.studio",
            smtp_password="password",
        ),
        email_sender_factory=sender_factory,
    ).process_pending()

    await test_db.refresh(event)

    assert delivered == 0
    assert event.status == "FAILED"
    assert event.error_message == "SMTP authentication failed (535): invalid credentials"
