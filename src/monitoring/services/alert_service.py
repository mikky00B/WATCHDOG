from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.alert import Alert
from monitoring.schemas.alert import AlertCreate, AlertUpdate, AlertSeverity

logger = structlog.get_logger(__name__)


class AlertService:
    """Business logic for alert management with deduplication."""

    def __init__(self, db: AsyncSession, deduplication_window_minutes: int = 15):
        self.db = db
        self.deduplication_window_minutes = deduplication_window_minutes

    async def create_alert(self, data: AlertCreate) -> Alert:
        """
        Create a new alert with deduplication check.

        Args:
            data: Alert creation data

        Returns:
            Created alert (or existing if deduplicated)
        """
        # Check for duplicate alerts within time window
        existing_alert = await self._find_duplicate_alert(data)

        if existing_alert:
            logger.info(
                "alert_deduplicated",
                alert_id=existing_alert.id,
                monitor_id=data.monitor_id,
                title=data.title,
            )
            return existing_alert

        # Create new alert
        alert = Alert(**data.model_dump())
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)

        logger.info(
            "alert_created",
            alert_id=alert.id,
            monitor_id=alert.monitor_id,
            severity=alert.severity,
            title=alert.title,
        )

        return alert

    async def _find_duplicate_alert(self, data: AlertCreate) -> Alert | None:
        """
        Find duplicate unresolved alert within deduplication window.

        Args:
            data: Alert data to check

        Returns:
            Existing alert if found, None otherwise
        """
        window_start = datetime.now(timezone.utc) - timedelta(
            minutes=self.deduplication_window_minutes
        )

        stmt = (
            select(Alert)
            .where(
                and_(
                    Alert.monitor_id == data.monitor_id,
                    Alert.severity == data.severity,
                    Alert.title == data.title,
                    Alert.resolved == False,  # noqa: E712
                    Alert.triggered_at >= window_start,
                )
            )
            .order_by(Alert.triggered_at.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_alert(self, alert_id: int) -> Alert | None:
        """
        Get alert by ID.

        Args:
            alert_id: Alert ID

        Returns:
            Alert if found, None otherwise
        """
        return await self.db.get(Alert, alert_id)

    async def list_alerts(
        self,
        skip: int = 0,
        limit: int = 100,
        unresolved_only: bool = False,
        monitor_id: int | None = None,
        severity: AlertSeverity | None = None,
    ) -> tuple[list[Alert], int]:
        """
        List alerts with pagination and filters.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            unresolved_only: Filter for unresolved alerts only
            monitor_id: Filter by monitor ID
            severity: Filter by severity level

        Returns:
            A tuple containing the list of alerts and the total count.
        """
        base_stmt = select(Alert)

        # Apply filters
        if unresolved_only:
            base_stmt = base_stmt.where(Alert.resolved == False)  # noqa: E712

        if monitor_id is not None:
            base_stmt = base_stmt.where(Alert.monitor_id == monitor_id)

        if severity is not None:
            base_stmt = base_stmt.where(Alert.severity == severity)

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = base_stmt.order_by(Alert.triggered_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        alerts = list(result.scalars().all())

        return alerts, total

    async def update_alert(self, alert_id: int, data: AlertUpdate) -> Alert | None:
        """
        Update alert.

        Args:
            alert_id: Alert ID
            data: Update data

        Returns:
            Updated alert if found, None otherwise
        """
        alert = await self.get_alert(alert_id)
        if alert is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(alert, key, value)

        await self.db.flush()
        await self.db.refresh(alert)

        logger.info(
            "alert_updated",
            alert_id=alert.id,
            resolved=alert.resolved,
            acknowledged=alert.acknowledged,
        )

        return alert

    async def resolve_alert(
        self, alert_id: int, note: str | None = None
    ) -> Alert | None:
        """
        Mark alert as resolved.

        Args:
            alert_id: Alert ID
            note: Optional resolution note

        Returns:
            Updated alert if found, None otherwise
        """
        update_data = AlertUpdate(
            resolved=True,
            resolved_at=datetime.now(timezone.utc),
        )

        alert = await self.update_alert(alert_id, update_data)

        if alert and note:
            logger.info(
                "alert_resolved_with_note",
                alert_id=alert_id,
                note=note,
            )

        return alert

    async def acknowledge_alert(self, alert_id: int) -> Alert | None:
        """
        Mark alert as acknowledged.

        Args:
            alert_id: Alert ID

        Returns:
            Updated alert if found, None otherwise
        """
        update_data = AlertUpdate(acknowledged=True)
        return await self.update_alert(alert_id, update_data)

    async def bulk_resolve_alerts(
        self,
        monitor_id: int,
        severity: AlertSeverity | None = None,
    ) -> int:
        """
        Bulk resolve all unresolved alerts for a monitor.

        Args:
            monitor_id: Monitor ID
            severity: Optional severity filter

        Returns:
            Number of alerts resolved
        """
        stmt = select(Alert).where(
            and_(
                Alert.monitor_id == monitor_id,
                Alert.resolved == False,  # noqa: E712
            )
        )

        if severity:
            stmt = stmt.where(Alert.severity == severity)

        result = await self.db.execute(stmt)
        alerts = list(result.scalars().all())

        resolved_count = 0
        for alert in alerts:
            alert.resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
            resolved_count += 1

        if resolved_count > 0:
            await self.db.flush()
            logger.info(
                "bulk_alerts_resolved",
                monitor_id=monitor_id,
                count=resolved_count,
                severity=severity.value if severity else "all",
            )

        return resolved_count

    async def get_alert_statistics(
        self,
        monitor_id: int | None = None,
        days: int = 7,
    ) -> dict:
        """
        Get alert statistics for a time period.

        Args:
            monitor_id: Optional monitor ID filter
            days: Number of days to look back

        Returns:
            Dictionary with alert statistics
        """
        window_start = datetime.now(timezone.utc) - timedelta(days=days)

        base_stmt = select(Alert).where(Alert.triggered_at >= window_start)

        if monitor_id:
            base_stmt = base_stmt.where(Alert.monitor_id == monitor_id)

        result = await self.db.execute(base_stmt)
        alerts = list(result.scalars().all())

        # Calculate statistics
        total = len(alerts)
        by_severity = {
            "critical": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
        }
        resolved = 0
        unresolved = 0

        for alert in alerts:
            by_severity[alert.severity] += 1
            if alert.resolved:
                resolved += 1
            else:
                unresolved += 1

        return {
            "total": total,
            "by_severity": by_severity,
            "resolved": resolved,
            "unresolved": unresolved,
            "resolution_rate": (resolved / total * 100) if total > 0 else 0,
            "period_days": days,
        }

    async def auto_resolve_old_alerts(self, days: int = 30) -> int:
        """
        Auto-resolve alerts older than specified days.

        Args:
            days: Number of days after which to auto-resolve

        Returns:
            Number of alerts auto-resolved
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(Alert).where(
            and_(
                Alert.triggered_at < cutoff_date,
                Alert.resolved == False,  # noqa: E712
            )
        )

        result = await self.db.execute(stmt)
        alerts = list(result.scalars().all())

        resolved_count = 0
        for alert in alerts:
            alert.resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
            resolved_count += 1

        if resolved_count > 0:
            await self.db.flush()
            logger.info(
                "auto_resolved_old_alerts",
                count=resolved_count,
                cutoff_days=days,
            )

        return resolved_count
