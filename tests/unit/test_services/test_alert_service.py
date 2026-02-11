"""Unit tests for AlertService."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.alert import Alert
from monitoring.schemas.alert import AlertCreate, AlertSeverity, AlertUpdate
from monitoring.services.alert_service import AlertService


def _alert_create(monitor_id: int, severity: str = "warning") -> AlertCreate:
    return AlertCreate(
        monitor_id=monitor_id,
        severity=AlertSeverity(severity),
        title=f"Test Alert [{severity}]",
        message="Something failed",
        triggered_at=datetime.utcnow(),
    )


@pytest.mark.unit
async def test_create_alert(test_db: AsyncSession, sample_monitor) -> None:
    service = AlertService(test_db)
    alert = await service.create_alert(_alert_create(sample_monitor.id))

    assert alert.id is not None
    assert alert.monitor_id == sample_monitor.id
    assert alert.severity == "warning"
    assert alert.resolved is False
    assert alert.acknowledged is False


@pytest.mark.unit
async def test_create_alert_critical(test_db: AsyncSession, sample_monitor) -> None:
    service = AlertService(test_db)
    alert = await service.create_alert(_alert_create(sample_monitor.id, "critical"))
    assert alert.severity == "critical"


@pytest.mark.unit
async def test_get_alert(test_db: AsyncSession, sample_alert: Alert) -> None:
    service = AlertService(test_db)
    found = await service.get_alert(sample_alert.id)
    assert found is not None
    assert found.id == sample_alert.id
    assert found.title == sample_alert.title


@pytest.mark.unit
async def test_get_alert_not_found(test_db: AsyncSession) -> None:
    service = AlertService(test_db)
    assert await service.get_alert(99999) is None


@pytest.mark.unit
async def test_list_alerts(test_db: AsyncSession, sample_alert: Alert) -> None:
    service = AlertService(test_db)
    alerts = await service.list_alerts()
    assert len(alerts) >= 1
    assert any(a.id == sample_alert.id for a in alerts)


@pytest.mark.unit
async def test_list_alerts_unresolved_only(test_db: AsyncSession, sample_monitor) -> None:
    service = AlertService(test_db)
    unresolved = await service.create_alert(_alert_create(sample_monitor.id))
    resolved = await service.create_alert(_alert_create(sample_monitor.id))
    await service.resolve_alert(resolved.id)
    await test_db.commit()

    open_alerts = await service.list_alerts(unresolved_only=True)
    ids = [a.id for a in open_alerts]
    assert unresolved.id in ids
    assert resolved.id not in ids


@pytest.mark.unit
async def test_update_alert(test_db: AsyncSession, sample_alert: Alert) -> None:
    service = AlertService(test_db)
    updated = await service.update_alert(sample_alert.id, AlertUpdate(acknowledged=True))
    assert updated is not None
    assert updated.acknowledged is True


@pytest.mark.unit
async def test_update_alert_not_found(test_db: AsyncSession) -> None:
    service = AlertService(test_db)
    assert await service.update_alert(99999, AlertUpdate(acknowledged=True)) is None


@pytest.mark.unit
async def test_resolve_alert(test_db: AsyncSession, sample_alert: Alert) -> None:
    service = AlertService(test_db)
    resolved = await service.resolve_alert(sample_alert.id)
    assert resolved is not None
    assert resolved.resolved is True
    assert resolved.resolved_at is not None


@pytest.mark.unit
async def test_acknowledge_alert(test_db: AsyncSession, sample_alert: Alert) -> None:
    service = AlertService(test_db)
    acked = await service.acknowledge_alert(sample_alert.id)
    assert acked is not None
    assert acked.acknowledged is True
