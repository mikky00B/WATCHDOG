from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.schemas.alert import AlertCreate, AlertSeverity

logger = structlog.get_logger(__name__)


class RuleType(str, Enum):
    """Types of alert rules."""

    CONSECUTIVE_FAILURES = "consecutive_failures"
    LATENCY_THRESHOLD = "latency_threshold"
    ERROR_RATE = "error_rate"
    HEARTBEAT_MISSED = "heartbeat_missed"
    UPTIME_PERCENTAGE = "uptime_percentage"  # New: Track uptime SLA
    STATUS_CODE_PATTERN = "status_code_pattern"  # New: Alert on specific status codes


@dataclass
class RuleConfig:
    """Configuration for a monitoring rule."""

    rule_type: RuleType
    threshold: int | float
    window_minutes: int = 5
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True  # Allow disabling rules without deleting them
    metadata: dict[str, Any] | None = None  # Additional rule-specific config

    def __post_init__(self):
        """Validate configuration."""
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")
        if self.window_minutes <= 0:
            raise ValueError("window_minutes must be positive")


class Rule(ABC):
    """Abstract base class for alert rules."""

    def __init__(self, config: RuleConfig):
        self.config = config

    @abstractmethod
    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """
        Evaluate the rule against latest check result.

        Args:
            monitor: The monitor being checked
            latest_result: Latest check result
            db: Database session

        Returns:
            AlertCreate if rule is triggered, None otherwise
        """
        pass

    def _get_window_start(self) -> datetime:
        """Get the start of the evaluation window with proper timezone."""
        return datetime.now(timezone.utc) - timedelta(
            minutes=self.config.window_minutes
        )


class ConsecutiveFailuresRule(Rule):
    """Triggers alert after N consecutive failures."""

    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """Evaluate consecutive failures."""
        # Early return if latest check succeeded
        if latest_result.success:
            return None

        threshold = int(self.config.threshold)

        # Query for the most recent N checks (where N = threshold)
        stmt = (
            select(CheckResult)
            .where(CheckResult.monitor_id == monitor.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(threshold)
        )

        result = await db.execute(stmt)
        recent_checks = list(result.scalars().all())

        # Need at least threshold number of checks
        if len(recent_checks) < threshold:
            logger.debug(
                "insufficient_checks_for_evaluation",
                monitor_id=monitor.id,
                checks_available=len(recent_checks),
                threshold=threshold,
            )
            return None

        # Check if all recent checks failed
        all_failed = all(not check.success for check in recent_checks)

        if all_failed:
            logger.warning(
                "consecutive_failures_detected",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                failure_count=len(recent_checks),
                threshold=threshold,
            )

            # Collect error messages for context
            error_messages = [
                check.error_message
                for check in recent_checks[:3]  # Show last 3
                if check.error_message
            ]
            error_context = (
                "; ".join(error_messages) if error_messages else "No error details"
            )

            return AlertCreate(
                monitor_id=monitor.id,
                severity=self.config.severity,
                title=f"Monitor '{monitor.name}' has {len(recent_checks)} consecutive failures",
                message=f"Recent errors: {error_context}",
                triggered_at=datetime.now(timezone.utc),
            )

        return None


class LatencyThresholdRule(Rule):
    """Triggers alert when latency exceeds threshold."""

    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """Evaluate latency threshold."""
        if latest_result.latency_ms is None:
            return None

        threshold_ms = float(self.config.threshold)

        if latest_result.latency_ms > threshold_ms:
            # Check if this is a sustained issue (optional: requires multiple violations)
            sustained_check = self.config.metadata and self.config.metadata.get(
                "require_sustained", False
            )

            if sustained_check:
                # Check last N results to see if latency is consistently high
                window_start = self._get_window_start()
                stmt = (
                    select(CheckResult)
                    .where(CheckResult.monitor_id == monitor.id)
                    .where(CheckResult.checked_at >= window_start)
                    .where(CheckResult.latency_ms.isnot(None))
                    .order_by(CheckResult.checked_at.desc())
                    .limit(3)
                )

                result = await db.execute(stmt)
                recent_checks = list(result.scalars().all())

                high_latency_count = sum(
                    1
                    for check in recent_checks
                    if check.latency_ms and check.latency_ms > threshold_ms
                )

                if high_latency_count < 2:  # Need at least 2 of last 3
                    return None

            logger.warning(
                "latency_threshold_exceeded",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                latency_ms=latest_result.latency_ms,
                threshold_ms=threshold_ms,
            )

            return AlertCreate(
                monitor_id=monitor.id,
                severity=self.config.severity,
                title=f"Monitor '{monitor.name}' latency exceeded threshold",
                message=(
                    f"Current latency: {latest_result.latency_ms:.2f}ms "
                    f"(threshold: {threshold_ms}ms)"
                ),
                triggered_at=datetime.now(timezone.utc),
            )

        return None


class ErrorRateRule(Rule):
    """Triggers alert when error rate exceeds threshold percentage."""

    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """Evaluate error rate over window."""
        window_start = self._get_window_start()

        # Get all checks in window
        stmt = (
            select(CheckResult)
            .where(CheckResult.monitor_id == monitor.id)
            .where(CheckResult.checked_at >= window_start)
        )

        result = await db.execute(stmt)
        checks = list(result.scalars().all())

        if len(checks) < 5:  # Need minimum sample size
            logger.debug(
                "insufficient_checks_for_error_rate",
                monitor_id=monitor.id,
                checks_available=len(checks),
            )
            return None

        # Calculate error rate
        failed_count = sum(1 for check in checks if not check.success)
        error_rate = (failed_count / len(checks)) * 100
        threshold_percentage = float(self.config.threshold)

        if error_rate >= threshold_percentage:
            logger.warning(
                "error_rate_threshold_exceeded",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                error_rate=error_rate,
                threshold=threshold_percentage,
                window_minutes=self.config.window_minutes,
            )

            return AlertCreate(
                monitor_id=monitor.id,
                severity=self.config.severity,
                title=f"Monitor '{monitor.name}' error rate exceeded threshold",
                message=(
                    f"Error rate: {error_rate:.1f}% ({failed_count}/{len(checks)} checks failed) "
                    f"in last {self.config.window_minutes} minutes "
                    f"(threshold: {threshold_percentage}%)"
                ),
                triggered_at=datetime.now(timezone.utc),
            )

        return None


class UptimePercentageRule(Rule):
    """Triggers alert when uptime falls below threshold percentage."""

    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """Evaluate uptime percentage over window."""
        window_start = self._get_window_start()

        # Get all checks in window
        stmt = (
            select(CheckResult)
            .where(CheckResult.monitor_id == monitor.id)
            .where(CheckResult.checked_at >= window_start)
        )

        result = await db.execute(stmt)
        checks = list(result.scalars().all())

        if len(checks) < 10:  # Need reasonable sample size for uptime
            return None

        # Calculate uptime
        success_count = sum(1 for check in checks if check.success)
        uptime_percentage = (success_count / len(checks)) * 100
        threshold_percentage = float(self.config.threshold)

        if uptime_percentage < threshold_percentage:
            logger.warning(
                "uptime_below_threshold",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                uptime=uptime_percentage,
                threshold=threshold_percentage,
                window_minutes=self.config.window_minutes,
            )

            return AlertCreate(
                monitor_id=monitor.id,
                severity=self.config.severity,
                title=f"Monitor '{monitor.name}' uptime below threshold",
                message=(
                    f"Uptime: {uptime_percentage:.2f}% ({success_count}/{len(checks)} successful) "
                    f"in last {self.config.window_minutes} minutes "
                    f"(threshold: {threshold_percentage}%)"
                ),
                triggered_at=datetime.now(timezone.utc),
            )

        return None


class StatusCodePatternRule(Rule):
    """Triggers alert on specific status code patterns."""

    async def evaluate(
        self,
        monitor: Monitor,
        latest_result: CheckResult,
        db: AsyncSession,
    ) -> AlertCreate | None:
        """Evaluate status code patterns."""
        if latest_result.status_code is None:
            return None

        # Get target status codes from metadata
        target_codes = (
            self.config.metadata.get("status_codes", []) if self.config.metadata else []
        )
        if not target_codes:
            return None

        if latest_result.status_code in target_codes:
            logger.warning(
                "status_code_pattern_matched",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                status_code=latest_result.status_code,
            )

            return AlertCreate(
                monitor_id=monitor.id,
                severity=self.config.severity,
                title=f"Monitor '{monitor.name}' returned status code {latest_result.status_code}",
                message=(
                    f"Received status code {latest_result.status_code} which matches alert pattern. "
                    f"Error: {latest_result.error_message or 'No error message'}"
                ),
                triggered_at=datetime.now(timezone.utc),
            )

        return None


class RuleEngine:
    """Evaluates monitoring rules and triggers alerts with deduplication."""

    def __init__(self) -> None:
        self.rules: dict[int, list[Rule]] = {}
        self._alert_cache: dict[tuple[int, str], datetime] = (
            {}
        )  # (monitor_id, rule_type) -> last_alert_time
        self._alert_cooldown_minutes = 15  # Don't re-alert within 15 minutes

    def register_rules(self, monitor_id: int, rules: list[Rule]) -> None:
        """
        Register rules for a monitor.

        Args:
            monitor_id: Internal monitor ID
            rules: List of rules to register
        """
        # Filter to only enabled rules
        enabled_rules = [rule for rule in rules if rule.config.enabled]
        self.rules[monitor_id] = enabled_rules

        logger.info(
            "rules_registered",
            monitor_id=monitor_id,
            total_rules=len(rules),
            enabled_rules=len(enabled_rules),
        )

    def unregister_rules(self, monitor_id: int) -> None:
        """
        Unregister all rules for a monitor.

        Args:
            monitor_id: Internal monitor ID
        """
        if monitor_id in self.rules:
            del self.rules[monitor_id]
            logger.info("rules_unregistered", monitor_id=monitor_id)

    def _should_alert(self, monitor_id: int, rule_type: str) -> bool:
        """Check if enough time has passed since last alert (deduplication)."""
        cache_key = (monitor_id, rule_type)
        last_alert = self._alert_cache.get(cache_key)

        if last_alert is None:
            return True

        time_since_last = datetime.now(timezone.utc) - last_alert
        return time_since_last.total_seconds() > (self._alert_cooldown_minutes * 60)

    def _record_alert(self, monitor_id: int, rule_type: str) -> None:
        """Record that an alert was triggered."""
        cache_key = (monitor_id, rule_type)
        self._alert_cache[cache_key] = datetime.now(timezone.utc)

    async def evaluate_all(
        self,
        monitor: Monitor,
        check_result: CheckResult,
        db: AsyncSession,
    ) -> list[AlertCreate]:
        """
        Evaluate all rules for a monitor with deduplication.

        Args:
            monitor: Monitor being checked
            check_result: Latest check result
            db: Database session

        Returns:
            List of alerts to create
        """
        alerts: list[AlertCreate] = []
        monitor_rules = self.rules.get(monitor.id, [])

        if not monitor_rules:
            logger.debug(
                "no_rules_registered",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
            )
            return alerts

        for rule in monitor_rules:
            try:
                # Check cooldown before evaluation
                if not self._should_alert(monitor.id, rule.config.rule_type.value):
                    logger.debug(
                        "alert_cooldown_active",
                        monitor_id=monitor.id,
                        rule_type=rule.config.rule_type.value,
                    )
                    continue

                # Evaluate the rule
                alert = await rule.evaluate(monitor, check_result, db)

                if alert:
                    alerts.append(alert)
                    self._record_alert(monitor.id, rule.config.rule_type.value)

                    logger.info(
                        "alert_triggered",
                        monitor_id=monitor.id,
                        rule_type=rule.config.rule_type.value,
                        severity=alert.severity.value,
                    )

            except Exception as exc:
                logger.error(
                    "rule_evaluation_error",
                    monitor_id=monitor.id,
                    rule_type=rule.config.rule_type.value,
                    error=str(exc),
                    exc_info=True,
                )
                # Continue evaluating other rules even if one fails

        return alerts

    async def get_monitor_rules(self, monitor_id: int) -> list[Rule]:
        """Get all registered rules for a monitor."""
        return self.rules.get(monitor_id, [])

    def clear_alert_cache(self, monitor_id: int | None = None) -> None:
        """
        Clear alert cooldown cache.

        Args:
            monitor_id: If provided, clear only for this monitor. Otherwise clear all.
        """
        if monitor_id is None:
            self._alert_cache.clear()
            logger.info("alert_cache_cleared_all")
        else:
            keys_to_remove = [
                key for key in self._alert_cache.keys() if key[0] == monitor_id
            ]
            for key in keys_to_remove:
                del self._alert_cache[key]
            logger.info("alert_cache_cleared", monitor_id=monitor_id)


# Convenience function to create standard rule sets
def create_default_rules() -> list[Rule]:
    """Create a default set of monitoring rules."""
    return [
        ConsecutiveFailuresRule(
            RuleConfig(
                rule_type=RuleType.CONSECUTIVE_FAILURES,
                threshold=3,
                severity=AlertSeverity.ERROR,
            )
        ),
        LatencyThresholdRule(
            RuleConfig(
                rule_type=RuleType.LATENCY_THRESHOLD,
                threshold=2000,  # 2 seconds
                severity=AlertSeverity.WARNING,
                metadata={"require_sustained": True},
            )
        ),
        ErrorRateRule(
            RuleConfig(
                rule_type=RuleType.ERROR_RATE,
                threshold=50,  # 50% error rate
                window_minutes=10,
                severity=AlertSeverity.ERROR,
            )
        ),
        UptimePercentageRule(
            RuleConfig(
                rule_type=RuleType.UPTIME_PERCENTAGE,
                threshold=95,  # 95% uptime
                window_minutes=60,
                severity=AlertSeverity.WARNING,
            )
        ),
    ]
