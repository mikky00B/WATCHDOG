from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.alert import Alert
from monitoring.models.check_result import CheckResult
from monitoring.models.client import Client
from monitoring.models.incident import Incident, IncidentUpdate
from monitoring.models.log_entry import LogEntry
from monitoring.models.monitor import Monitor
from monitoring.services.maintenance_service import MaintenanceService
from monitoring.utils.time_period import bucket_seconds_for

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """Cross-cutting analytics for dashboards: charts, health, timelines."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def response_time_series(
        self,
        organization_id: int,
        hours: float,
        monitor_id: int | None = None,
        client_id: int | None = None,
    ) -> list[dict[str, object]]:
        """Average and p95 response time per time bucket."""
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=hours)
        stmt = (
            select(CheckResult.checked_at, CheckResult.latency_ms, CheckResult.monitor_id)
            .where(
                CheckResult.organization_id == organization_id,
                CheckResult.checked_at >= window_start,
                CheckResult.latency_ms.is_not(None),
            )
            .order_by(CheckResult.checked_at.asc())
            .limit(50000)
        )
        if monitor_id is not None:
            stmt = stmt.where(CheckResult.monitor_id == monitor_id)
        rows = (await self.db.execute(stmt)).all()

        monitor_client: dict[int, int | None] = {}
        if client_id is not None:
            monitor_rows = await self.db.execute(
                select(Monitor.id, Monitor.client_id).where(
                    Monitor.organization_id == organization_id,
                ),
            )
            monitor_client = dict(monitor_rows.all())

        bucket_seconds = bucket_seconds_for(hours)
        buckets: dict[int, list[float]] = {}
        for checked_at, latency_ms, result_monitor_id in rows:
            if client_id is not None and monitor_client.get(result_monitor_id) != client_id:
                continue
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=UTC)
            index = int(checked_at.timestamp()) // bucket_seconds
            buckets.setdefault(index, []).append(float(latency_ms))

        series: list[dict[str, object]] = []
        for index in sorted(buckets):
            values = sorted(buckets[index])
            series.append(
                {
                    "bucket": datetime.fromtimestamp(index * bucket_seconds, tz=UTC),
                    "avg_ms": round(sum(values) / len(values), 1),
                    "p95_ms": round(values[int(len(values) * 0.95) - 1], 1) if values else None,
                    "count": len(values),
                },
            )
        return series

    async def uptime_series(
        self,
        organization_id: int,
        hours: float,
        monitor_id: int | None = None,
    ) -> list[dict[str, object]]:
        """Uptime percentage per time bucket."""
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=hours)
        stmt = (
            select(CheckResult.checked_at, CheckResult.success)
            .where(
                CheckResult.organization_id == organization_id,
                CheckResult.checked_at >= window_start,
            )
            .order_by(CheckResult.checked_at.asc())
            .limit(50000)
        )
        if monitor_id is not None:
            stmt = stmt.where(CheckResult.monitor_id == monitor_id)
        rows = (await self.db.execute(stmt)).all()

        bucket_seconds = bucket_seconds_for(hours)
        buckets: dict[int, dict[str, int]] = {}
        for checked_at, success in rows:
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=UTC)
            index = int(checked_at.timestamp()) // bucket_seconds
            bucket = buckets.setdefault(index, {"total": 0, "success": 0})
            bucket["total"] += 1
            if success:
                bucket["success"] += 1

        series: list[dict[str, object]] = []
        for index in sorted(buckets):
            values = buckets[index]
            series.append(
                {
                    "bucket": datetime.fromtimestamp(index * bucket_seconds, tz=UTC),
                    "uptime_percentage": round(
                        (values["success"] / values["total"]) * 100,
                        2,
                    )
                    if values["total"]
                    else None,
                    "total_checks": values["total"],
                },
            )
        return series

    async def service_health(self, organization_id: int) -> dict[str, object]:
        """Per-monitor health overview with 24h uptime and latency."""
        monitors = (
            await self.db.execute(
                select(Monitor).where(Monitor.organization_id == organization_id),
            )
        ).scalars().all()

        clients = {
            client.id: client.name
            for client in (
                await self.db.execute(
                    select(Client).where(Client.organization_id == organization_id),
                )
            ).scalars().all()
        }

        suppressed_ids = await MaintenanceService(self.db).get_suppressed_monitor_ids()

        window_start = datetime.now(UTC) - timedelta(hours=24)
        stats_rows = await self.db.execute(
            select(
                CheckResult.monitor_id,
                CheckResult.success,
                CheckResult.latency_ms,
            ).where(
                CheckResult.organization_id == organization_id,
                CheckResult.checked_at >= window_start,
            ),
        )
        per_monitor: dict[int, dict[str, float]] = {}
        for result_monitor_id, success, latency_ms in stats_rows.all():
            stats = per_monitor.setdefault(
                result_monitor_id,
                {"total": 0, "success": 0, "latency_sum": 0.0, "latency_count": 0},
            )
            stats["total"] += 1
            if success:
                stats["success"] += 1
            if latency_ms is not None:
                stats["latency_sum"] += float(latency_ms)
                stats["latency_count"] += 1

        now = datetime.now(UTC)
        services: list[dict[str, object]] = []
        counts = {"UP": 0, "DOWN": 0, "DEGRADED": 0, "MAINTENANCE": 0, "OTHER": 0}
        for monitor in monitors:
            stats = per_monitor.get(monitor.id, {"total": 0, "success": 0, "latency_sum": 0.0, "latency_count": 0})
            in_maintenance = monitor.id in suppressed_ids
            status = "MAINTENANCE" if in_maintenance else monitor.status
            status_key = status if status in counts else "OTHER"
            counts[status_key] = counts.get(status_key, 0) + 1

            ssl_days_remaining = None
            if monitor.ssl_expires_at is not None:
                expires_at = monitor.ssl_expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                ssl_days_remaining = round((expires_at - now).total_seconds() / 86400, 1)

            services.append(
                {
                    "public_id": monitor.public_id,
                    "name": monitor.name,
                    "monitor_type": monitor.monitor_type,
                    "status": status,
                    "environment": monitor.environment,
                    "tags": monitor.tags or [],
                    "client_name": clients.get(monitor.client_id),
                    "in_maintenance": in_maintenance,
                    "uptime_24h": round(
                        (stats["success"] / stats["total"]) * 100,
                        2,
                    )
                    if stats["total"]
                    else None,
                    "avg_latency_24h": round(
                        stats["latency_sum"] / stats["latency_count"],
                        1,
                    )
                    if stats["latency_count"]
                    else None,
                    "total_checks_24h": int(stats["total"]),
                    "ssl_days_remaining": ssl_days_remaining,
                    "last_checked_at": monitor.last_checked_at,
                },
            )

        return {"services": services, "counts": counts}

    async def incident_timeline(self, incident: Incident) -> dict[str, object]:
        """Correlated timeline for one incident: updates, alerts, checks, log errors."""
        started_at = incident.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        ended_at = incident.resolved_at or datetime.now(UTC)
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=UTC)

        events: list[dict[str, object]] = []

        events.append(
            {
                "kind": "incident",
                "timestamp": started_at,
                "message": incident.reason or incident.title,
                "severity": incident.severity,
            },
        )

        updates = (
            await self.db.execute(
                select(IncidentUpdate)
                .where(IncidentUpdate.incident_id == incident.id)
                .order_by(IncidentUpdate.created_at.asc()),
            )
        ).scalars().all()
        for update in updates:
            events.append(
                {
                    "kind": "update",
                    "timestamp": update.created_at,
                    "message": update.message,
                    "visibility": update.visibility,
                },
            )

        alerts = (
            await self.db.execute(
                select(Alert)
                .where(
                    Alert.monitor_id == incident.monitor_id,
                    Alert.triggered_at >= started_at - timedelta(minutes=5),
                    Alert.triggered_at <= ended_at + timedelta(minutes=5),
                )
                .order_by(Alert.triggered_at.asc()),
            )
        ).scalars().all()
        for alert in alerts:
            events.append(
                {
                    "kind": "alert",
                    "timestamp": alert.triggered_at,
                    "message": alert.title,
                    "severity": alert.severity,
                },
            )

        failed_checks = (
            await self.db.execute(
                select(CheckResult)
                .where(
                    CheckResult.monitor_id == incident.monitor_id,
                    CheckResult.checked_at >= started_at - timedelta(minutes=5),
                    CheckResult.checked_at <= ended_at + timedelta(minutes=5),
                    CheckResult.success.is_(False),
                )
                .order_by(CheckResult.checked_at.asc())
                .limit(20),
            )
        ).scalars().all()
        for check in failed_checks:
            events.append(
                {
                    "kind": "check",
                    "timestamp": check.checked_at,
                    "message": check.error_message or "Check failed",
                    "status_code": check.status_code,
                },
            )

        if incident.organization_id is not None:
            log_errors = (
                await self.db.execute(
                    select(LogEntry)
                    .where(
                        LogEntry.organization_id == incident.organization_id,
                        LogEntry.level.in_(["ERROR", "CRITICAL"]),
                        LogEntry.timestamp >= started_at - timedelta(minutes=5),
                        LogEntry.timestamp <= ended_at + timedelta(minutes=5),
                    )
                    .order_by(LogEntry.timestamp.asc())
                    .limit(20),
                )
            ).scalars().all()
            for entry in log_errors:
                events.append(
                    {
                        "kind": "log",
                        "timestamp": entry.timestamp,
                        "message": f"[{entry.application}] {entry.message[:300]}",
                        "level": entry.level,
                        "trace_id": entry.trace_id,
                    },
                )

        # Normalize naive (SQLite) datetimes before sorting.
        for event in events:
            if event["timestamp"] is not None and event["timestamp"].tzinfo is None:
                event["timestamp"] = event["timestamp"].replace(tzinfo=UTC)
        events.sort(key=lambda event: event["timestamp"])
        return {
            "incident": {
                "id": incident.id,
                "title": incident.title,
                "status": incident.status,
                "severity": incident.severity,
                "started_at": incident.started_at,
                "resolved_at": incident.resolved_at,
                "duration_seconds": incident.duration_seconds,
            },
            "events": events,
        }
