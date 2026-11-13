from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.alert import Alert
from monitoring.models.host_metric import HostMetric, HostThreshold
from monitoring.models.notification import NotificationChannel
from monitoring.models.organization import Organization
from monitoring.schemas.alert import AlertSeverity
from monitoring.schemas.infrastructure import HostMetricIngest, HostSummary
from monitoring.services.notification_service import AlertEventService

logger = structlog.get_logger(__name__)

# When a metric sits within 10% below its threshold, mark the host WARNING.
WARNING_MARGIN = 0.9


class InfrastructureService:
    """Ingestion, querying, and threshold alerting for host metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_metrics(
        self,
        organization_id: int,
        metrics: list[HostMetricIngest],
        client_id: int | None = None,
    ) -> int:
        now = datetime.now(UTC)
        accepted = 0
        for metric in metrics:
            timestamp = metric.timestamp
            if timestamp is None:
                timestamp = now
            elif timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            self.db.add(
                HostMetric(
                    organization_id=organization_id,
                    client_id=client_id,
                    host=metric.host[:255],
                    environment=metric.environment,
                    cpu_percent=metric.cpu_percent,
                    memory_percent=metric.memory_percent,
                    memory_used_mb=metric.memory_used_mb,
                    disk_percent=metric.disk_percent,
                    disk_used_gb=metric.disk_used_gb,
                    net_in_kb_per_s=metric.net_in_kb_per_s,
                    net_out_kb_per_s=metric.net_out_kb_per_s,
                    processes=list(metric.processes) if metric.processes else None,
                    service_checks=dict(metric.service_checks) if metric.service_checks else None,
                    measured_at=timestamp,
                ),
            )
            accepted += 1
        if accepted:
            await self.db.flush()
        return accepted

    async def get_threshold(self, organization_id: int, host: str) -> HostThreshold | None:
        result = await self.db.execute(
            select(HostThreshold).where(
                HostThreshold.organization_id == organization_id,
                HostThreshold.host == host,
            ),
        )
        return result.scalar_one_or_none()

    async def upsert_threshold(self, organization_id: int, data) -> HostThreshold:
        threshold = await self.get_threshold(organization_id, data.host)
        if threshold is None:
            threshold = HostThreshold(organization_id=organization_id)
            self.db.add(threshold)
        threshold.host = data.host
        threshold.cpu_percent = data.cpu_percent
        threshold.memory_percent = data.memory_percent
        threshold.disk_percent = data.disk_percent
        threshold.process_names = list(data.process_names) if data.process_names else None
        threshold.enabled = True
        await self.db.flush()
        await self.db.refresh(threshold)
        return threshold

    async def list_thresholds(
        self,
        organization_id: int,
    ) -> list[HostThreshold]:
        result = await self.db.execute(
            select(HostThreshold)
            .where(HostThreshold.organization_id == organization_id)
            .order_by(HostThreshold.host),
        )
        return list(result.scalars().all())

    async def update_threshold(self, threshold_id: int, data) -> HostThreshold | None:
        threshold = await self.db.get(HostThreshold, threshold_id)
        if threshold is None:
            return None
        values = data.model_dump(exclude_unset=True)
        if "process_names" in values and values["process_names"] is not None:
            values["process_names"] = list(values["process_names"])
        for key, value in values.items():
            setattr(threshold, key, value)
        await self.db.flush()
        await self.db.refresh(threshold)
        return threshold

    async def delete_threshold(self, threshold_id: int) -> bool:
        threshold = await self.db.get(HostThreshold, threshold_id)
        if threshold is None:
            return False
        await self.db.delete(threshold)
        return True

    async def list_hosts(
        self,
        organization_id: int,
        history_hours: float = 6.0,
    ) -> list[HostSummary]:
        """Latest state of every host plus recent samples and thresholds."""
        window_start = datetime.now(UTC) - timedelta(hours=history_hours)
        base_stmt = select(HostMetric).where(
            HostMetric.organization_id == organization_id,
            HostMetric.measured_at >= window_start,
        )
        hosts_rows = await self.db.execute(
            select(HostMetric.host).distinct().where(
                HostMetric.organization_id == organization_id,
                HostMetric.measured_at >= window_start,
            ),
        )
        host_names = [row[0] for row in hosts_rows.all()]

        summaries: list[HostSummary] = []
        for host in sorted(host_names):
            history_result = await self.db.execute(
                base_stmt.where(HostMetric.host == host).order_by(HostMetric.measured_at.asc()),
            )
            history = list(history_result.scalars().all())
            latest = history[-1] if history else None
            threshold = await self.get_threshold(organization_id, host)
            summaries.append(
                HostSummary(
                    host=host,
                    environment=latest.environment if latest else None,
                    latest=latest,  # type: ignore[arg-type]
                    history=history,  # type: ignore[arg-type]
                    threshold=threshold,  # type: ignore[arg-type]
                    health=self._health(latest, threshold) if latest else "UNKNOWN",
                ),
            )
        return summaries

    def _health(self, metric: HostMetric, threshold: HostThreshold | None) -> str:
        if threshold is None or not threshold.enabled:
            return "OK"
        checks = [
            (metric.cpu_percent, threshold.cpu_percent),
            (metric.memory_percent, threshold.memory_percent),
            (metric.disk_percent, threshold.disk_percent),
        ]
        critical = False
        warning = False
        for value, limit in checks:
            if value is None or limit is None:
                continue
            if value > limit:
                critical = True
            elif value >= limit * WARNING_MARGIN:
                warning = True
        service_checks = metric.service_checks or {}
        for name in threshold.process_names or []:
            if service_checks.get(str(name)) is False:
                critical = True
        if critical:
            return "CRITICAL"
        if warning:
            return "WARNING"
        return "OK"

    async def evaluate_thresholds(self) -> list[Alert]:
        """Evaluate all enabled host thresholds against the latest metric.

        Creates deduplicated alerts and queues notification events for the
        organization's active channels. Intended to run on a schedule.
        """
        now = datetime.now(UTC)
        thresholds = (
            await self.db.execute(
                select(HostThreshold).where(HostThreshold.enabled == True),  # noqa: E712
            )
        ).scalars().all()

        created: list[Alert] = []
        for threshold in thresholds:
            latest = (
                await self.db.execute(
                    select(HostMetric)
                    .where(
                        HostMetric.organization_id == threshold.organization_id,
                        HostMetric.host == threshold.host,
                    )
                    .order_by(HostMetric.measured_at.desc())
                    .limit(1),
                )
            ).scalar_one_or_none()
            if latest is None:
                continue
            # Only evaluate fresh metrics (within 15 minutes).
            measured_at = latest.measured_at
            if measured_at.tzinfo is None:
                measured_at = measured_at.replace(tzinfo=UTC)
            if now - measured_at > timedelta(minutes=15):
                continue

            breaches = self._breaches(latest, threshold)
            if not breaches:
                continue

            severity = (
                AlertSeverity.CRITICAL
                if any(level == "critical" for level, _ in breaches)
                else AlertSeverity.WARNING
            )
            description = "; ".join(detail for _, detail in breaches)
            title = f"Host '{threshold.host}' resource threshold breached"

            # Deduplicate: skip if the same unresolved alert fired recently.
            window_start = now - timedelta(minutes=15)
            existing = (
                await self.db.execute(
                    select(Alert)
                    .where(
                        Alert.organization_id == threshold.organization_id,
                        Alert.monitor_id.is_(None),
                        Alert.title == title,
                        Alert.resolved.is_(False),
                        Alert.triggered_at >= window_start,
                    )
                    .limit(1),
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            alert = Alert(
                monitor_id=None,
                severity=severity.value,
                title=title,
                message=description,
                triggered_at=now,
            )
            alert.organization_id = threshold.organization_id
            self.db.add(alert)
            await self.db.flush()
            await self.db.refresh(alert)
            created.append(alert)
            await self._queue_notification(threshold.organization_id, description)

        if created:
            await self.db.commit()
        return created

    def _breaches(self, metric: HostMetric, threshold: HostThreshold) -> list[tuple[str, str]]:
        breaches: list[tuple[str, str]] = []
        if (
            threshold.cpu_percent is not None
            and metric.cpu_percent is not None
            and metric.cpu_percent > threshold.cpu_percent
        ):
            breaches.append(
                ("critical", f"CPU {metric.cpu_percent:.1f}% > {threshold.cpu_percent:.0f}%"),
            )
        if (
            threshold.memory_percent is not None
            and metric.memory_percent is not None
            and metric.memory_percent > threshold.memory_percent
        ):
            breaches.append(
                (
                    "critical",
                    f"Memory {metric.memory_percent:.1f}% > {threshold.memory_percent:.0f}%",
                ),
            )
        if (
            threshold.disk_percent is not None
            and metric.disk_percent is not None
            and metric.disk_percent > threshold.disk_percent
        ):
            breaches.append(
                ("critical", f"Disk {metric.disk_percent:.1f}% > {threshold.disk_percent:.0f}%"),
            )
        service_checks = metric.service_checks or {}
        for name in threshold.process_names or []:
            if service_checks.get(str(name)) is False:
                breaches.append(("critical", f"Service '{name}' is not running"))
        return breaches

    async def _queue_notification(self, organization_id: int, message: str) -> None:
        channels = (
            await self.db.execute(
                select(NotificationChannel).where(
                    NotificationChannel.organization_id == organization_id,
                    NotificationChannel.is_active.is_(True),
                ),
            )
        ).scalars().all()
        event_service = AlertEventService(self.db)
        for channel in channels:
            await event_service.queue_event(
                organization_id=organization_id,
                monitor_id=None,
                incident_id=None,
                channel_id=channel.id,
                event_type="INFRA_THRESHOLD",
                message=message,
            )

    async def delete_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(delete(HostMetric).where(HostMetric.measured_at < cutoff))
        await self.db.commit()
        return result.rowcount or 0


async def resolve_organization(db: AsyncSession, public_id) -> Organization | None:
    result = await db.execute(
        select(Organization).where(Organization.public_id == public_id),
    )
    return result.scalar_one_or_none()


async def resolve_client(db: AsyncSession, public_id):
    """Resolve a client by public UUID."""
    from monitoring.models.client import Client

    result = await db.execute(select(Client).where(Client.public_id == public_id))
    return result.scalar_one_or_none()
