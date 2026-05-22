from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.database import AsyncSessionLocal
from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.services.alert_service import AlertService
from monitoring.services.checker_service import CheckerService
from monitoring.services.incident_service import IncidentService
from monitoring.services.rule_engine import (
    RuleEngine,
    create_default_rules,
)

logger = structlog.get_logger(__name__)


class MonitorScheduler:
    """Schedules and executes periodic monitor checks."""

    def __init__(
        self,
        checker_service: CheckerService,
        rule_engine: RuleEngine,
    ):
        self.checker_service = checker_service
        self.rule_engine = rule_engine
        self.running = False
        self._registered_monitors: set[int] = set()  # Track which monitors have rules

    async def start(self) -> None:
        """Start the scheduler."""
        self.running = True
        logger.info("scheduler_started")

        # Register rules for all active monitors on startup
        await self._initialize_rules()

        while self.running:
            try:
                await self._run_checks()
                await asyncio.sleep(10)  # Check every 10 seconds for due monitors
            except Exception as exc:
                logger.error("scheduler_error", error=str(exc), exc_info=True)
                await asyncio.sleep(10)

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
        logger.info("scheduler_stopped")

    async def _initialize_rules(self) -> None:
        """Initialize rules for all active monitors on startup."""
        async with AsyncSessionLocal() as db:
            stmt = select(Monitor).where(Monitor.enabled == True)  # noqa: E712
            result = await db.execute(stmt)
            monitors = list(result.scalars().all())

            for monitor in monitors:
                self._register_monitor_rules(monitor)

            logger.info(
                "rules_initialized",
                monitor_count=len(monitors),
            )

    def _register_monitor_rules(self, monitor: Monitor) -> None:
        """
        Register rules for a monitor if not already registered.

        Args:
            monitor: Monitor to register rules for
        """
        # Skip if already registered
        if monitor.id in self._registered_monitors:
            return

        # Create default rules for the monitor
        rules = create_default_rules()

        # TODO: In the future, you can customize rules based on monitor properties
        # For example:
        # if hasattr(monitor, 'custom_thresholds'):
        #     rules = self._create_custom_rules(monitor)

        self.rule_engine.register_rules(monitor.id, rules)
        self._registered_monitors.add(monitor.id)

        logger.info(
            "monitor_rules_registered",
            monitor_id=monitor.id,
            monitor_name=monitor.name,
            rule_count=len(rules),
        )

    async def _run_checks(self) -> None:
        """Run checks for all monitors that are due."""
        async with AsyncSessionLocal() as db:
            stmt = select(Monitor).where(Monitor.enabled == True)  # noqa: E712
            result = await db.execute(stmt)
            monitors = list(result.scalars().all())

            # Register rules for any new monitors
            for monitor in monitors:
                self._register_monitor_rules(monitor)

            await self._record_missed_heartbeats(monitors, db)

            # Check which monitors are due
            due_monitors = [m for m in monitors if self._is_check_due(m)]

            if due_monitors:
                logger.info(
                    "running_checks",
                    total_monitors=len(monitors),
                    due_monitors=len(due_monitors),
                )

                # Run checks concurrently
                tasks = [self._check_monitor(monitor, db) for monitor in due_monitors]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Log any exceptions that occurred
                for monitor, outcome in zip(due_monitors, results, strict=False):
                    if isinstance(outcome, Exception):
                        logger.error(
                            "check_task_failed",
                            monitor_id=monitor.id,
                            monitor_name=monitor.name,
                            error=str(outcome),
                        )

    def _is_check_due(self, monitor: Monitor) -> bool:
        """
        Check if monitor is due for a check.

        Args:
            monitor: Monitor to check

        Returns:
            True if check is due, False otherwise
        """
        if monitor.last_checked_at is None:
            if monitor.monitor_type == "HEARTBEAT":
                return False
            return True

        if monitor.monitor_type == "HEARTBEAT":
            return False

        now = datetime.now(UTC)
        if monitor.next_check_at is not None:
            next_check_at = monitor.next_check_at
            if next_check_at.tzinfo is None:
                next_check_at = next_check_at.replace(tzinfo=UTC)
            return next_check_at <= now

        last_checked_at = monitor.last_checked_at
        if last_checked_at.tzinfo is None:
            last_checked_at = last_checked_at.replace(tzinfo=UTC)
        elapsed = (now - last_checked_at).total_seconds()
        return elapsed >= monitor.interval_seconds

    async def _record_missed_heartbeats(
        self,
        monitors: list[Monitor],
        db: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        missed_count = 0

        for monitor in monitors:
            if monitor.monitor_type != "HEARTBEAT" or monitor.next_check_at is None:
                continue

            next_check_at = monitor.next_check_at
            if next_check_at.tzinfo is None:
                next_check_at = next_check_at.replace(tzinfo=UTC)

            if next_check_at > now:
                continue

            monitor.consecutive_failures += 1
            monitor.consecutive_successes = 0
            monitor.status = "DOWN"
            monitor.last_checked_at = now
            monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
            db.add(
                CheckResult(
                    monitor_id=monitor.id,
                    organization_id=monitor.organization_id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message="Heartbeat missed",
                    checked_at=now,
                )
            )
            await IncidentService(db).create_or_update_for_failed_check(
                monitor,
                "Heartbeat missed",
            )
            missed_count += 1

        if missed_count:
            await db.commit()

    async def _check_monitor(self, monitor: Monitor, db: AsyncSession) -> None:
        """
        Perform check on a single monitor.

        Args:
            monitor: Monitor to check
            db: Database session
        """
        try:
            logger.debug(
                "checking_monitor",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                url=monitor.url,
            )

            # Perform the check
            check_result = await self.checker_service.check_http_endpoint(monitor)
            check_result.organization_id = monitor.organization_id

            # Save result
            db.add(check_result)

            # Update monitor last_checked_at (use timezone-aware datetime)
            monitor.last_checked_at = datetime.now(UTC)
            monitor.next_check_at = monitor.last_checked_at + timedelta(
                seconds=monitor.interval_seconds,
            )
            if check_result.success:
                monitor.status = "UP"
                monitor.consecutive_successes += 1
                monitor.consecutive_failures = 0
                await IncidentService(db).resolve_for_monitor(
                    monitor,
                    note="Monitor recovered automatically",
                )
            else:
                monitor.status = "DOWN"
                monitor.consecutive_failures += 1
                monitor.consecutive_successes = 0
                await IncidentService(db).create_or_update_for_failed_check(
                    monitor,
                    check_result.error_message or "Monitor check failed",
                )

            await db.commit()
            await db.refresh(check_result)

            logger.info(
                "check_completed",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                success=check_result.success,
                status_code=check_result.status_code,
                latency_ms=check_result.latency_ms,
            )

            # Evaluate rules and create alerts
            alerts = await self.rule_engine.evaluate_all(monitor, check_result, db)

            if alerts:
                logger.info(
                    "alerts_triggered",
                    monitor_id=monitor.id,
                    alert_count=len(alerts),
                )

                alert_service = AlertService(db)
                for alert_data in alerts:
                    try:
                        alert = await alert_service.create_alert(alert_data)
                        alert.organization_id = monitor.organization_id
                    except Exception as exc:
                        logger.error(
                            "alert_creation_failed",
                            monitor_id=monitor.id,
                            error=str(exc),
                            exc_info=True,
                        )

                await db.commit()

        except Exception as exc:
            await db.rollback()  # Rollback on error
            logger.error(
                "check_monitor_error",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                error=str(exc),
                exc_info=True,
            )
            raise  # Re-raise so gather() can catch it

    async def reload_monitor_rules(self, monitor_id: int) -> None:
        """
        Reload rules for a specific monitor.
        Useful when monitor configuration changes.

        Args:
            monitor_id: Internal monitor ID
        """
        async with AsyncSessionLocal() as db:
            stmt = select(Monitor).where(Monitor.id == monitor_id)
            result = await db.execute(stmt)
            monitor = result.scalar_one_or_none()

            if monitor:
                # Clear existing rules
                self.rule_engine.unregister_rules(monitor_id)
                self._registered_monitors.discard(monitor_id)

                # Re-register
                self._register_monitor_rules(monitor)

                logger.info(
                    "monitor_rules_reloaded",
                    monitor_id=monitor_id,
                    monitor_name=monitor.name,
                )
            else:
                logger.warning(
                    "monitor_not_found_for_reload",
                    monitor_id=monitor_id,
                )

    async def remove_monitor(self, monitor_id: int) -> None:
        """
        Remove a monitor from the scheduler.
        Useful when a monitor is deleted.

        Args:
            monitor_id: Internal monitor ID
        """
        self.rule_engine.unregister_rules(monitor_id)
        self._registered_monitors.discard(monitor_id)

        logger.info(
            "monitor_removed_from_scheduler",
            monitor_id=monitor_id,
        )
