"""Unit tests for the Rule Engine — uses SQLite in-memory DB."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.schemas.alert import AlertSeverity
from monitoring.services.rule_engine import (
    ConsecutiveFailuresRule,
    LatencyThresholdRule,
    RuleConfig,
    RuleEngine,
    RuleType,
)


def _result(monitor_id: int, success: bool, latency_ms: float | None = 100.0,
            offset_secs: int = 0) -> CheckResult:
    return CheckResult(
        monitor_id=monitor_id,
        success=success,
        latency_ms=latency_ms,
        status_code=200 if success else 503,
        error_message=None if success else "Service Unavailable",
        checked_at=datetime.utcnow() - timedelta(seconds=offset_secs),
    )


def _failures_rule(threshold: int = 3) -> ConsecutiveFailuresRule:
    return ConsecutiveFailuresRule(RuleConfig(
        rule_type=RuleType.CONSECUTIVE_FAILURES,
        threshold=threshold,
        window_minutes=10,
        severity=AlertSeverity.ERROR,
    ))


def _latency_rule(threshold_ms: float = 500.0) -> LatencyThresholdRule:
    return LatencyThresholdRule(RuleConfig(
        rule_type=RuleType.LATENCY_THRESHOLD,
        threshold=threshold_ms,
        window_minutes=5,
        severity=AlertSeverity.WARNING,
    ))


# ── ConsecutiveFailuresRule ───────────────────────────────────────────────────

@pytest.mark.unit
async def test_consecutive_failures_no_trigger_on_success(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _failures_rule(3)
    latest = _result(sample_monitor.id, success=True)
    alert = await rule.evaluate(sample_monitor, latest, test_db)
    assert alert is None


@pytest.mark.unit
async def test_consecutive_failures_triggers_at_threshold(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    # Seed 3 failures within the window
    for i in range(3):
        test_db.add(_result(sample_monitor.id, success=False, offset_secs=i * 30))
    await test_db.commit()

    rule = _failures_rule(3)
    latest = _result(sample_monitor.id, success=False)
    alert = await rule.evaluate(sample_monitor, latest, test_db)

    assert alert is not None
    assert alert.monitor_id == sample_monitor.id
    assert alert.severity == AlertSeverity.ERROR
    assert "consecutive" in alert.title.lower()


@pytest.mark.unit
async def test_consecutive_failures_not_enough_history(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    # Only 2 failures, threshold=3
    for i in range(2):
        test_db.add(_result(sample_monitor.id, success=False, offset_secs=i * 10))
    await test_db.commit()

    rule = _failures_rule(3)
    latest = _result(sample_monitor.id, success=False)
    assert await rule.evaluate(sample_monitor, latest, test_db) is None


@pytest.mark.unit
async def test_consecutive_failures_mixed_no_trigger(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    # 1 success followed by 2 failures — not all failures
    test_db.add(_result(sample_monitor.id, success=True,  offset_secs=60))
    test_db.add(_result(sample_monitor.id, success=False, offset_secs=30))
    test_db.add(_result(sample_monitor.id, success=False, offset_secs=10))
    await test_db.commit()

    rule = _failures_rule(3)
    latest = _result(sample_monitor.id, success=False)
    assert await rule.evaluate(sample_monitor, latest, test_db) is None


@pytest.mark.unit
async def test_consecutive_failures_threshold_1(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    # Threshold of 1 fires immediately on any failure
    rule = _failures_rule(1)
    latest = _result(sample_monitor.id, success=False)
    # Need at least 1 in DB
    test_db.add(_result(sample_monitor.id, success=False, offset_secs=5))
    await test_db.commit()

    alert = await rule.evaluate(sample_monitor, latest, test_db)
    assert alert is not None


# ── LatencyThresholdRule ──────────────────────────────────────────────────────

@pytest.mark.unit
async def test_latency_no_trigger_under_threshold(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _latency_rule(500.0)
    latest = _result(sample_monitor.id, success=True, latency_ms=100.0)
    assert await rule.evaluate(sample_monitor, latest, test_db) is None


@pytest.mark.unit
async def test_latency_triggers_over_threshold(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _latency_rule(500.0)
    latest = _result(sample_monitor.id, success=True, latency_ms=1500.0)
    alert = await rule.evaluate(sample_monitor, latest, test_db)

    assert alert is not None
    assert alert.severity == AlertSeverity.WARNING
    assert "1500" in alert.message
    assert "500" in alert.message


@pytest.mark.unit
async def test_latency_no_trigger_exact_threshold(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _latency_rule(500.0)
    latest = _result(sample_monitor.id, success=True, latency_ms=500.0)
    # Exactly equal: not strictly greater, should not fire
    assert await rule.evaluate(sample_monitor, latest, test_db) is None


@pytest.mark.unit
async def test_latency_none_latency_no_trigger(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _latency_rule(500.0)
    latest = _result(sample_monitor.id, success=False, latency_ms=None)
    assert await rule.evaluate(sample_monitor, latest, test_db) is None


@pytest.mark.unit
async def test_latency_rule_title_contains_monitor_name(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    rule = _latency_rule(100.0)
    latest = _result(sample_monitor.id, success=True, latency_ms=999.0)
    alert = await rule.evaluate(sample_monitor, latest, test_db)
    assert sample_monitor.name in alert.title


# ── RuleEngine orchestrator ───────────────────────────────────────────────────

@pytest.mark.unit
async def test_rule_engine_no_rules_returns_empty(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    engine = RuleEngine()
    latest = _result(sample_monitor.id, success=False)
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    assert alerts == []


@pytest.mark.unit
async def test_rule_engine_registers_and_fires(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    engine = RuleEngine()
    engine.register_rules(sample_monitor.id, [_latency_rule(100.0)])

    latest = _result(sample_monitor.id, success=True, latency_ms=9999.0)
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    assert len(alerts) == 1


@pytest.mark.unit
async def test_rule_engine_multiple_rules_both_fire(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    # Seed failures for the consecutive rule
    for i in range(3):
        test_db.add(_result(sample_monitor.id, success=False, offset_secs=i * 10))
    await test_db.commit()

    engine = RuleEngine()
    engine.register_rules(sample_monitor.id, [
        _failures_rule(3),
        _latency_rule(1.0),  # any latency triggers this
    ])
    latest = _result(sample_monitor.id, success=False, latency_ms=500.0)
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    assert len(alerts) == 2


@pytest.mark.unit
async def test_rule_engine_unregistered_monitor_returns_empty(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    engine = RuleEngine()
    engine.register_rules(9999, [_latency_rule(100.0)])  # different monitor ID

    latest = _result(sample_monitor.id, success=False, latency_ms=9999.0)
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    assert alerts == []


@pytest.mark.unit
async def test_rule_engine_overwrite_rules(
    test_db: AsyncSession, sample_monitor: Monitor
) -> None:
    engine = RuleEngine()
    engine.register_rules(sample_monitor.id, [_latency_rule(1.0)])
    engine.register_rules(sample_monitor.id, [_latency_rule(99999.0)])  # overwrite

    latest = _result(sample_monitor.id, success=True, latency_ms=500.0)
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    # New threshold is very high, should not fire
    assert alerts == []
