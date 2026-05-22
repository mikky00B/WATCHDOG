from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from monitoring.models.check_result import CheckResult
from monitoring.models.incident import Incident
from monitoring.models.monitor import Monitor
from monitoring.services.checker_service import CheckerService
from monitoring.services.rule_engine import RuleEngine
from monitoring.workers.scheduler import MonitorScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
async def test_scheduler_records_missed_heartbeat(test_db: AsyncSession) -> None:
    monitor = Monitor(
        name="Daily Backup",
        monitor_type="HEARTBEAT",
        heartbeat_key="hb_test",
        interval_seconds=60,
        next_check_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    test_db.add(monitor)
    await test_db.commit()
    await test_db.refresh(monitor)

    scheduler = MonitorScheduler(CheckerService(), RuleEngine())
    await scheduler._record_missed_heartbeats([monitor], test_db)
    await test_db.refresh(monitor)

    result = await test_db.execute(
        select(CheckResult).where(CheckResult.monitor_id == monitor.id)
    )
    check = result.scalar_one()

    assert check.success is False
    assert check.error_message == "Heartbeat missed"
    assert monitor.status == "DOWN"
    assert monitor.consecutive_failures == 1
    assert monitor.consecutive_successes == 0
    assert monitor.next_check_at is not None

    incident_result = await test_db.execute(
        select(Incident).where(Incident.monitor_id == monitor.id)
    )
    incident = incident_result.scalar_one()
    assert incident.status == "OPEN"
    assert incident.reason == "Heartbeat missed"


@pytest.mark.unit
async def test_scheduler_resolves_incident_on_recovery(test_db: AsyncSession) -> None:
    monitor = Monitor(name="API", url="https://api.example.com", interval_seconds=60)
    test_db.add(monitor)
    await test_db.commit()
    await test_db.refresh(monitor)

    checker = CheckerService()
    scheduler = MonitorScheduler(checker, RuleEngine())

    from monitoring.models.check_result import CheckResult

    checker.check_http_endpoint = AsyncMock(
        return_value=CheckResult(
            monitor_id=monitor.id,
            status_code=500,
            latency_ms=10,
            success=False,
            error_message="HTTP 500",
            checked_at=datetime.now(UTC),
        )
    )
    await scheduler._check_monitor(monitor, test_db)

    checker.check_http_endpoint = AsyncMock(
        return_value=CheckResult(
            monitor_id=monitor.id,
            status_code=200,
            latency_ms=10,
            success=True,
            error_message=None,
            checked_at=datetime.now(UTC),
        )
    )
    monitor.last_checked_at = datetime.now(UTC) - timedelta(seconds=120)
    await scheduler._check_monitor(monitor, test_db)

    result = await test_db.execute(select(Incident).where(Incident.monitor_id == monitor.id))
    incident = result.scalar_one()
    assert incident.status == "RESOLVED"
    assert incident.resolved_at is not None
