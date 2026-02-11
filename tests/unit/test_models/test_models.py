"""Unit tests for ORM models — structural and default value tests."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.alert import Alert
from monitoring.models.check_result import CheckResult
from monitoring.models.heartbeat import Heartbeat
from monitoring.models.monitor import Monitor


@pytest.mark.unit
async def test_monitor_defaults(test_db: AsyncSession) -> None:
    m = Monitor(name="API", url="https://x.com", interval_seconds=60)
    test_db.add(m)
    await test_db.commit()
    await test_db.refresh(m)

    assert m.id is not None
    assert isinstance(m.public_id, uuid.UUID)
    assert m.enabled is True
    assert m.monitor_type == "http"
    assert m.timeout_seconds == 5.0
    assert m.last_checked_at is None


@pytest.mark.unit
async def test_monitor_repr(test_db: AsyncSession) -> None:
    m = Monitor(name="API", url="https://x.com", interval_seconds=60)
    test_db.add(m)
    await test_db.commit()
    assert "API" in repr(m)
    assert "Monitor" in repr(m)


@pytest.mark.unit
async def test_monitor_unique_public_ids(test_db: AsyncSession) -> None:
    m1 = Monitor(name="A", url="https://a.com", interval_seconds=60)
    m2 = Monitor(name="B", url="https://b.com", interval_seconds=60)
    test_db.add(m1)
    test_db.add(m2)
    await test_db.commit()
    assert m1.public_id != m2.public_id


@pytest.mark.unit
async def test_check_result_defaults(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    cr = CheckResult(
        monitor_id=sample_monitor.id,
        status_code=200,
        latency_ms=55.0,
        success=True,
        checked_at=datetime.utcnow(),
    )
    test_db.add(cr)
    await test_db.commit()
    await test_db.refresh(cr)

    assert cr.id is not None
    assert cr.error_message is None


@pytest.mark.unit
async def test_check_result_failure(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    cr = CheckResult(
        monitor_id=sample_monitor.id,
        status_code=None,
        latency_ms=None,
        success=False,
        error_message="timeout",
        checked_at=datetime.utcnow(),
    )
    test_db.add(cr)
    await test_db.commit()
    await test_db.refresh(cr)

    assert cr.success is False
    assert cr.error_message == "timeout"


@pytest.mark.unit
async def test_alert_defaults(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    a = Alert(
        monitor_id=sample_monitor.id,
        severity="warning",
        title="Test", message="msg",
        triggered_at=datetime.utcnow(),
    )
    test_db.add(a)
    await test_db.commit()
    await test_db.refresh(a)

    assert a.id is not None
    assert a.resolved is False
    assert a.acknowledged is False
    assert a.resolved_at is None


@pytest.mark.unit
async def test_alert_repr(test_db: AsyncSession, sample_alert: Alert) -> None:
    assert "Alert" in repr(sample_alert)
    assert str(sample_alert.monitor_id) in repr(sample_alert)


@pytest.mark.unit
async def test_heartbeat_defaults(test_db: AsyncSession) -> None:
    hb = Heartbeat(name="Job", expected_interval_seconds=600)
    test_db.add(hb)
    await test_db.commit()
    await test_db.refresh(hb)

    assert hb.id is not None
    assert isinstance(hb.public_id, uuid.UUID)
    assert hb.last_heartbeat_at is None
    assert hb.description is None


@pytest.mark.unit
async def test_monitor_cascade_deletes_check_results(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    cr = CheckResult(
        monitor_id=sample_monitor.id, status_code=200,
        latency_ms=10.0, success=True, checked_at=datetime.utcnow(),
    )
    test_db.add(cr)
    await test_db.commit()

    await test_db.delete(sample_monitor)
    await test_db.commit()

    from sqlalchemy import select
    remaining = await test_db.execute(select(CheckResult).where(CheckResult.id == cr.id))
    assert remaining.scalar_one_or_none() is None
