from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.database import AsyncSessionLocal
from monitoring.models.monitor import Monitor
from monitoring.services.alert_service import AlertService
from monitoring.services.checker_service import CheckerService
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
                for monitor, result in zip(due_monitors, results):
                    if isinstance(result, Exception):
                        logger.error(
                            "check_task_failed",
                            monitor_id=monitor.id,
                            monitor_name=monitor.name,
                            error=str(result),
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
            return True

        elapsed = (datetime.now(timezone.utc) - monitor.last_checked_at).total_seconds()
        return elapsed >= monitor.interval_seconds

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

            # Save result
            db.add(check_result)

            # Update monitor last_checked_at (use timezone-aware datetime)
            monitor.last_checked_at = datetime.now(timezone.utc)

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
                        await alert_service.create_alert(alert_data)
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
