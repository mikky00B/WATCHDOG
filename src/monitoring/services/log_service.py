from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.log_entry import LogEntry
from monitoring.schemas.log import LogEntryIngest
from monitoring.utils.redaction import redact_attributes, redact_text
from monitoring.utils.time_period import bucket_seconds_for

logger = structlog.get_logger(__name__)

MAX_MESSAGE_LENGTH = 8000
MAX_ATTRIBUTES_JSON_CHARS = 16000


class LogService:
    """Ingestion, search, statistics, and retention for application logs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(
        self,
        organization_id: int,
        entries: list[LogEntryIngest],
        default_application: str | None = None,
        default_environment: str | None = None,
        client_id: int | None = None,
    ) -> tuple[int, int]:
        """Persist a batch of log entries with redaction applied.

        Returns (accepted, rejected) counts. Invalid entries are skipped, not
        fatal — a partial batch is better than dropping everything.
        """
        accepted = 0
        rejected = 0
        now = datetime.now(UTC)

        for entry in entries:
            application = (entry.application or default_application or "").strip()
            if not application:
                rejected += 1
                continue
            level = entry.normalized_level()
            if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                rejected += 1
                continue

            message = redact_text(entry.message)[:MAX_MESSAGE_LENGTH]
            attributes = None
            if entry.attributes:
                attributes = redact_attributes(entry.attributes)

            timestamp = entry.timestamp
            if timestamp is None:
                timestamp = now
            elif timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)

            self.db.add(
                LogEntry(
                    organization_id=organization_id,
                    client_id=client_id,
                    application=application[:255],
                    environment=(entry.environment or default_environment),
                    level=level,
                    message=message,
                    logger_name=entry.logger_name,
                    host=entry.host,
                    trace_id=entry.trace_id,
                    span_id=entry.span_id,
                    attributes=attributes,
                    timestamp=timestamp,
                ),
            )
            accepted += 1

        if accepted:
            await self.db.flush()
        if rejected:
            logger.warning(
                "log_ingest_rejections",
                organization_id=organization_id,
                rejected=rejected,
            )
        return accepted, rejected

    async def search_logs(
        self,
        organization_id: int,
        application: str | None = None,
        environment: str | None = None,
        level: str | None = None,
        client_id: int | None = None,
        search: str | None = None,
        trace_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[LogEntry], int]:
        """Search logs with org isolation and filters."""
        base_stmt = select(LogEntry).where(LogEntry.organization_id == organization_id)
        if application:
            base_stmt = base_stmt.where(LogEntry.application == application)
        if environment:
            base_stmt = base_stmt.where(LogEntry.environment == environment)
        if level:
            levels = [part.strip().upper() for part in level.split(",") if part.strip()]
            if levels:
                base_stmt = base_stmt.where(LogEntry.level.in_(levels))
        if client_id is not None:
            base_stmt = base_stmt.where(LogEntry.client_id == client_id)
        if trace_id:
            base_stmt = base_stmt.where(LogEntry.trace_id == trace_id)
        if since is not None:
            base_stmt = base_stmt.where(LogEntry.timestamp >= since)
        if until is not None:
            base_stmt = base_stmt.where(LogEntry.timestamp <= until)
        if search:
            pattern = f"%{search}%"
            base_stmt = base_stmt.where(
                or_(
                    LogEntry.message.ilike(pattern),
                    LogEntry.application.ilike(pattern),
                    LogEntry.logger_name.ilike(pattern),
                ),
            )

        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(LogEntry.timestamp.desc(), LogEntry.id.desc())
            .offset(skip)
            .limit(limit),
        )
        return list(result.scalars().all()), total

    async def stats(
        self,
        organization_id: int,
        hours: float,
        application: str | None = None,
        client_id: int | None = None,
    ) -> dict[str, object]:
        """Log-volume statistics for charts: totals, by level, time buckets, errors."""
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=hours)

        base_filters = [
            LogEntry.organization_id == organization_id,
            LogEntry.timestamp >= window_start,
        ]
        if application:
            base_filters.append(LogEntry.application == application)
        if client_id is not None:
            base_filters.append(LogEntry.client_id == client_id)

        total = (
            await self.db.execute(
                select(func.count()).select_from(
                    select(LogEntry.id).where(*base_filters).subquery(),
                ),
            )
        ).scalar() or 0

        by_level_rows = await self.db.execute(
            select(LogEntry.level, func.count())
            .where(*base_filters)
            .group_by(LogEntry.level),
        )
        by_level = dict(by_level_rows.all())

        errors_by_application_rows = await self.db.execute(
            select(LogEntry.application, func.count())
            .where(
                *base_filters,
                LogEntry.level.in_(["ERROR", "CRITICAL"]),
            )
            .group_by(LogEntry.application),
        )
        errors_by_application = dict(errors_by_application_rows.all())

        # Volume buckets (bucketing in Python keeps this portable across dialects)
        bucket_seconds = bucket_seconds_for(hours)
        rows = await self.db.execute(
            select(LogEntry.timestamp, LogEntry.level)
            .where(*base_filters)
            .order_by(LogEntry.timestamp.asc())
            .limit(50000),
        )
        buckets: dict[int, dict[str, int]] = {}
        for timestamp, level in rows.all():
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            bucket_index = int(timestamp.timestamp()) // bucket_seconds
            bucket = buckets.setdefault(bucket_index, {"total": 0, "error": 0})
            bucket["total"] += 1
            if level in {"ERROR", "CRITICAL"}:
                bucket["error"] += 1

        from monitoring.schemas.log import LogVolumeBucket

        volume = [
            LogVolumeBucket(
                bucket=datetime.fromtimestamp(
                    index * bucket_seconds,
                    tz=UTC,
                ),
                total=values["total"],
                error=values["error"],
            )
            for index, values in sorted(buckets.items())
        ]

        return {
            "total": total,
            "by_level": by_level,
            "error_count": by_level.get("ERROR", 0) + by_level.get("CRITICAL", 0),
            "volume": volume,
            "errors_by_application": errors_by_application,
        }

    async def delete_older_than(self, days: int) -> int:
        """Retention cleanup: delete logs older than the given number of days."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(delete(LogEntry).where(LogEntry.timestamp < cutoff))
        await self.db.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info("log_retention_cleanup", deleted=deleted, days=days)
        return deleted
