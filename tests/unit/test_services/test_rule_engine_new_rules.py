"""Tests for the SSL expiring and anomaly detection rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.schemas.alert import AlertSeverity
from monitoring.services.rule_engine import (
    AnomalyRule,
    RuleConfig,
    RuleType,
    SSLExpiringRule,
)


def _make_monitor(**kwargs) -> Monitor:
    defaults = {
        "id": 1,
        "name": "Test",
        "url": "https://api.example.com",
        "monitor_type": "SSL",
        "interval_seconds": 60,
    }
    defaults.update(kwargs)
    return Monitor(**defaults)


def _ssl_rule(threshold_days: int = 14) -> SSLExpiringRule:
    return SSLExpiringRule(
        RuleConfig(rule_type=RuleType.SSL_EXPIRING, threshold=threshold_days),
    )


class TestSSLExpiringRule:
    async def test_ignores_non_ssl_monitors(self, test_db) -> None:
        monitor = _make_monitor(monitor_type="WEBSITE")
        monitor.ssl_expires_at = datetime.now(UTC) + timedelta(days=2)
        result = CheckResult(monitor_id=1, success=True, checked_at=datetime.now(UTC))
        rule = _ssl_rule()
        assert await rule.evaluate(monitor, result, test_db) is None

    async def test_no_expiry_date_is_none(self, test_db) -> None:
        monitor = _make_monitor()
        result = CheckResult(monitor_id=1, success=True, checked_at=datetime.now(UTC))
        assert await _ssl_rule().evaluate(monitor, result, test_db) is None

    async def test_expired_raises_critical(self, test_db) -> None:
        monitor = _make_monitor()
        monitor.ssl_expires_at = datetime.now(UTC) - timedelta(days=1)
        result = CheckResult(monitor_id=1, success=False, checked_at=datetime.now(UTC))
        alert = await _ssl_rule().evaluate(monitor, result, test_db)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL
        assert "expired" in alert.title.lower()

    async def test_expiring_raises_warning(self, test_db) -> None:
        monitor = _make_monitor(ssl_expiry_threshold_days=14)
        monitor.ssl_expires_at = datetime.now(UTC) + timedelta(days=5)
        result = CheckResult(monitor_id=1, success=True, checked_at=datetime.now(UTC))
        alert = await _ssl_rule().evaluate(monitor, result, test_db)
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert "expires" in alert.title.lower()

    async def test_healthy_certificate_is_none(self, test_db) -> None:
        monitor = _make_monitor(ssl_expiry_threshold_days=14)
        monitor.ssl_expires_at = datetime.now(UTC) + timedelta(days=90)
        result = CheckResult(monitor_id=1, success=True, checked_at=datetime.now(UTC))
        assert await _ssl_rule().evaluate(monitor, result, test_db) is None


class TestAnomalyRule:
    def _anomaly_rule(self, z: float = 3.0) -> AnomalyRule:
        return AnomalyRule(RuleConfig(rule_type=RuleType.ANOMALY, threshold=z))

    async def _seed_history(self, test_db, monitor: Monitor, latencies: list[float]) -> None:
        now = datetime.now(UTC)
        for index, latency in enumerate(latencies):
            test_db.add(
                CheckResult(
                    monitor_id=monitor.id,
                    success=True,
                    latency_ms=latency,
                    checked_at=now - timedelta(minutes=len(latencies) - index),
                ),
            )
        await test_db.flush()

    async def test_spike_triggers_alert(self, test_db) -> None:
        monitor = _make_monitor(monitor_type="WEBSITE")
        # 12 stable baseline checks around 100ms
        await self._seed_history(test_db, monitor, [100.0 + (index % 3) for index in range(12)])
        spike = CheckResult(
            monitor_id=monitor.id,
            success=True,
            latency_ms=5000.0,
            checked_at=datetime.now(UTC),
        )
        test_db.add(spike)
        await test_db.flush()
        alert = await self._anomaly_rule().evaluate(monitor, spike, test_db)
        assert alert is not None
        assert "anomaly" in alert.title.lower()

    async def test_insufficient_samples_is_none(self, test_db) -> None:
        monitor = _make_monitor(monitor_type="WEBSITE")
        await self._seed_history(test_db, monitor, [100.0] * 5)
        latest = CheckResult(
            monitor_id=monitor.id,
            success=True,
            latency_ms=9000.0,
            checked_at=datetime.now(UTC),
        )
        test_db.add(latest)
        await test_db.flush()
        assert await self._anomaly_rule().evaluate(monitor, latest, test_db) is None

    async def test_normal_latency_is_none(self, test_db) -> None:
        monitor = _make_monitor(monitor_type="WEBSITE")
        await self._seed_history(test_db, monitor, [100.0 + (index % 3) for index in range(12)])
        latest = CheckResult(
            monitor_id=monitor.id,
            success=True,
            latency_ms=110.0,
            checked_at=datetime.now(UTC),
        )
        test_db.add(latest)
        await test_db.flush()
        assert await self._anomaly_rule().evaluate(monitor, latest, test_db) is None

    async def test_failed_check_is_none(self, test_db) -> None:
        monitor = _make_monitor(monitor_type="WEBSITE")
        await self._seed_history(test_db, monitor, [100.0] * 12)
        latest = CheckResult(
            monitor_id=monitor.id,
            success=False,
            latency_ms=9000.0,
            checked_at=datetime.now(UTC),
        )
        test_db.add(latest)
        await test_db.flush()
        assert await self._anomaly_rule().evaluate(monitor, latest, test_db) is None
