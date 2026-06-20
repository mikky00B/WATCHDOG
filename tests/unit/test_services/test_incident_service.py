from __future__ import annotations

from datetime import UTC, datetime

import pytest
from monitoring.models.monitor import Monitor
from monitoring.models.notification import AlertEvent, NotificationChannel
from monitoring.schemas.incident import IncidentCreate
from monitoring.services.incident_service import IncidentService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
async def test_create_incident_deduplicates_open_incident(
    test_db: AsyncSession,
    sample_monitor: Monitor,
) -> None:
    service = IncidentService(test_db)
    first = await service.create_incident(
        IncidentCreate(
            monitor_id=sample_monitor.id,
            title="API down",
            reason="timeout",
            started_at=datetime.now(UTC),
        )
    )
    second = await service.create_incident(
        IncidentCreate(
            monitor_id=sample_monitor.id,
            title="API down again",
            reason="still timeout",
            started_at=datetime.now(UTC),
        )
    )

    assert first.id == second.id


@pytest.mark.unit
async def test_create_incident_queues_alert_event(
    test_db: AsyncSession,
    sample_monitor: Monitor,
) -> None:
    channel = NotificationChannel(
        name="Email",
        channel_type="EMAIL",
        config={"email": "alerts@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    incident = await IncidentService(test_db).create_or_update_for_failed_check(
        sample_monitor,
        "HTTP 500",
    )

    from sqlalchemy import select

    result = await test_db.execute(
        select(AlertEvent).where(AlertEvent.incident_id == incident.id)
    )
    event = result.scalar_one()
    assert event.event_type == "MONITOR_DOWN"
    assert event.status == "PENDING"


@pytest.mark.unit
async def test_resolve_for_monitor_sets_duration(
    test_db: AsyncSession,
    sample_monitor: Monitor,
) -> None:
    service = IncidentService(test_db)
    incident = await service.create_or_update_for_failed_check(sample_monitor, "HTTP 500")
    resolved = await service.resolve_for_monitor(sample_monitor)

    assert incident.id == resolved.id
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_at is not None
    assert resolved.duration_seconds is not None


@pytest.mark.unit
async def test_acknowledge_incident_does_not_queue_recovery_email(
    test_db: AsyncSession,
    sample_monitor: Monitor,
) -> None:
    channel = NotificationChannel(
        name="Email",
        channel_type="EMAIL",
        config={"email": "alerts@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    service = IncidentService(test_db)
    incident = await service.create_or_update_for_failed_check(sample_monitor, "HTTP 500")
    await service.acknowledge_incident(incident.id, note="Investigating")

    result = await test_db.execute(
        select(AlertEvent.event_type).where(AlertEvent.incident_id == incident.id)
    )

    assert list(result.scalars().all()) == ["MONITOR_DOWN"]


@pytest.mark.unit
async def test_resolve_incident_queues_recovery_email(
    test_db: AsyncSession,
    sample_monitor: Monitor,
) -> None:
    channel = NotificationChannel(
        name="Email",
        channel_type="EMAIL",
        config={"email": "alerts@example.com"},
    )
    test_db.add(channel)
    await test_db.flush()

    service = IncidentService(test_db)
    incident = await service.create_or_update_for_failed_check(sample_monitor, "HTTP 500")
    await service.resolve_incident(incident.id, note="Recovered")

    result = await test_db.execute(
        select(AlertEvent.event_type, AlertEvent.message)
        .where(AlertEvent.incident_id == incident.id)
        .order_by(AlertEvent.id)
    )

    assert result.all() == [("MONITOR_DOWN", "HTTP 500"), ("MONITOR_RECOVERED", "Recovered")]
