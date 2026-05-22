from __future__ import annotations

import calendar
import html
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from monitoring.models.check_result import CheckResult
from monitoring.models.client import Client
from monitoring.models.incident import Incident
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.schemas.report import (
    MonthlyReportResponse,
    ReportIncidentSummary,
    ReportMonitorSummary,
)


class ReportService:
    """Server-side reliability report calculations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_monthly_report(
        self,
        organization_id: uuid.UUID,
        year: int,
        month: int,
        client_id: uuid.UUID | None = None,
    ) -> MonthlyReportResponse | None:
        organization = await self._get_organization(organization_id)
        if organization is None:
            return None

        client = None
        if client_id is not None:
            client = await self._get_client(client_id)
            if client is None or client.organization_id != organization.id:
                return None

        period_start, period_end = self._month_bounds(year, month)
        monitors = await self._get_monitors(organization.id, client.id if client else None)
        monitor_ids = [monitor.id for monitor in monitors]
        checks = await self._get_checks(monitor_ids, period_start, period_end)
        incidents = await self._get_incidents(
            organization.id,
            monitor_ids,
            period_start,
            period_end,
        )

        checks_by_monitor: dict[int, list[CheckResult]] = {monitor.id: [] for monitor in monitors}
        for check in checks:
            checks_by_monitor.setdefault(check.monitor_id, []).append(check)

        incidents_by_monitor: dict[int, list[Incident]] = {monitor.id: [] for monitor in monitors}
        for incident in incidents:
            incidents_by_monitor.setdefault(incident.monitor_id, []).append(incident)

        monitor_summaries = [
            self._monitor_summary(
                monitor,
                checks_by_monitor.get(monitor.id, []),
                incidents_by_monitor.get(monitor.id, []),
                period_start,
                period_end,
            )
            for monitor in monitors
        ]

        total_checks = sum(summary.total_checks for summary in monitor_summaries)
        successful_checks = sum(summary.successful_checks for summary in monitor_summaries)
        uptime = round((successful_checks / total_checks) * 100, 2) if total_checks else 0.0
        latencies = [check.latency_ms for check in checks if check.latency_ms is not None]
        average_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
        incident_summaries = [
            ReportIncidentSummary(
                id=incident.id,
                monitor_id=incident.monitor.public_id,
                monitor_name=incident.monitor.name,
                title=incident.title,
                status=incident.status,
                severity=incident.severity,
                started_at=incident.started_at,
                resolved_at=incident.resolved_at,
                duration_seconds=incident.duration_seconds,
            )
            for incident in incidents
        ]

        return MonthlyReportResponse(
            organization_id=organization.public_id,
            organization_name=organization.name,
            client_id=client.public_id if client else None,
            client_name=client.name if client else "All clients",
            period_start=period_start,
            period_end=period_end,
            monitors_included=len(monitors),
            uptime_percentage=uptime,
            total_downtime_seconds=sum(
                self._incident_overlap_seconds(incident, period_start, period_end)
                for incident in incidents
            ),
            incident_count=len(incidents),
            average_response_time_ms=average_latency,
            monitors=monitor_summaries,
            incidents=incident_summaries,
        )

    def render_monthly_report_html(self, report: MonthlyReportResponse) -> str:
        period = report.period_start.strftime("%B %Y")
        downtime = self._format_duration(report.total_downtime_seconds)
        latency = (
            f"{report.average_response_time_ms:.2f} ms"
            if report.average_response_time_ms is not None
            else "No data"
        )
        monitor_rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(monitor.name)}</td>"
            f"<td>{html.escape(monitor.monitor_type)}</td>"
            f"<td>{monitor.uptime_percentage:.2f}%</td>"
            f"<td>{self._format_duration(monitor.downtime_seconds)}</td>"
            f"<td>{monitor.incident_count}</td>"
            f"<td>{self._format_latency(monitor.average_response_time_ms)}</td>"
            "</tr>"
            for monitor in report.monitors
        )
        incident_rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(incident.monitor_name)}</td>"
            f"<td>{html.escape(incident.title)}</td>"
            f"<td>{html.escape(incident.severity)}</td>"
            f"<td>{html.escape(incident.status)}</td>"
            f"<td>{incident.started_at:%Y-%m-%d %H:%M}</td>"
            f"<td>{self._format_duration(incident.duration_seconds or 0)}</td>"
            "</tr>"
            for incident in report.incidents
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report.client_name)} Reliability Report</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; color: #172033; margin: 40px; }}
    header {{ border-bottom: 1px solid #d8dee9; padding-bottom: 24px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    .muted {{ color: #5f6b7a; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
    .metric {{ border: 1px solid #d8dee9; border-radius: 8px; padding: 16px; }}
    .metric span {{ color: #5f6b7a; display: block; font-size: 13px; margin-bottom: 8px; }}
    .metric strong {{ font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0 32px; }}
    th, td {{ border-bottom: 1px solid #e5e9f0; padding: 12px; text-align: left; }}
    th {{ color: #5f6b7a; font-size: 12px; text-transform: uppercase; }}
  </style>
</head>
<body>
  <header>
    <div class="muted">{html.escape(report.organization_name)}</div>
    <h1>{html.escape(report.client_name)} Reliability Report</h1>
    <div class="muted">{html.escape(period)}</div>
  </header>
  <section class="metrics">
    <div class="metric"><span>Uptime</span><strong>{report.uptime_percentage:.2f}%</strong></div>
    <div class="metric"><span>Total downtime</span><strong>{downtime}</strong></div>
    <div class="metric"><span>Incidents</span><strong>{report.incident_count}</strong></div>
    <div class="metric"><span>Avg response</span><strong>{latency}</strong></div>
  </section>
  <h2>Monitors Included</h2>
  <table>
    <thead><tr><th>Name</th><th>Type</th><th>Uptime</th><th>Downtime</th><th>Incidents</th><th>Avg response</th></tr></thead>
    <tbody>{monitor_rows or '<tr><td colspan="6">No monitors in this report.</td></tr>'}</tbody>
  </table>
  <h2>Incident List</h2>
  <table>
    <thead><tr><th>Monitor</th><th>Title</th><th>Severity</th><th>Status</th><th>Started</th><th>Duration</th></tr></thead>
    <tbody>{incident_rows or '<tr><td colspan="6">No incidents in this period.</td></tr>'}</tbody>
  </table>
</body>
</html>"""

    async def _get_organization(self, organization_id: uuid.UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(Organization.public_id == organization_id),
        )
        return result.scalar_one_or_none()

    async def _get_client(self, client_id: uuid.UUID) -> Client | None:
        result = await self.db.execute(select(Client).where(Client.public_id == client_id))
        return result.scalar_one_or_none()

    async def _get_monitors(
        self,
        organization_id: int,
        client_id: int | None,
    ) -> list[Monitor]:
        stmt = select(Monitor).where(Monitor.organization_id == organization_id)
        if client_id is not None:
            stmt = stmt.where(Monitor.client_id == client_id)
        result = await self.db.execute(stmt.order_by(Monitor.name.asc()))
        return list(result.scalars().all())

    async def _get_checks(
        self,
        monitor_ids: list[int],
        period_start: datetime,
        period_end: datetime,
    ) -> list[CheckResult]:
        if not monitor_ids:
            return []
        result = await self.db.execute(
            select(CheckResult)
            .where(
                CheckResult.monitor_id.in_(monitor_ids),
                CheckResult.checked_at >= period_start,
                CheckResult.checked_at < period_end,
            )
            .order_by(CheckResult.checked_at.asc()),
        )
        return list(result.scalars().all())

    async def _get_incidents(
        self,
        organization_id: int,
        monitor_ids: list[int],
        period_start: datetime,
        period_end: datetime,
    ) -> list[Incident]:
        if not monitor_ids:
            return []
        result = await self.db.execute(
            select(Incident)
            .options(selectinload(Incident.monitor))
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .where(
                Incident.organization_id == organization_id,
                Incident.monitor_id.in_(monitor_ids),
                Incident.started_at < period_end,
                or_(Incident.resolved_at.is_(None), Incident.resolved_at >= period_start),
            )
            .order_by(Incident.started_at.asc()),
        )
        return list(result.scalars().all())

    def _monitor_summary(
        self,
        monitor: Monitor,
        checks: list[CheckResult],
        incidents: list[Incident],
        period_start: datetime,
        period_end: datetime,
    ) -> ReportMonitorSummary:
        successful_checks = sum(1 for check in checks if check.success)
        total_checks = len(checks)
        uptime = round((successful_checks / total_checks) * 100, 2) if total_checks else 0.0
        latencies = [check.latency_ms for check in checks if check.latency_ms is not None]
        average_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
        return ReportMonitorSummary(
            monitor_id=monitor.public_id,
            name=monitor.name,
            monitor_type=monitor.monitor_type,
            status=monitor.status,
            total_checks=total_checks,
            successful_checks=successful_checks,
            failed_checks=total_checks - successful_checks,
            uptime_percentage=uptime,
            downtime_seconds=sum(
                self._incident_overlap_seconds(incident, period_start, period_end)
                for incident in incidents
            ),
            incident_count=len(incidents),
            average_response_time_ms=average_latency,
        )

    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
        period_start = datetime(year, month, 1, tzinfo=UTC).replace(tzinfo=None)
        if month == 12:
            period_end = datetime(year + 1, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        else:
            period_end = datetime(year, month + 1, 1, tzinfo=UTC).replace(tzinfo=None)
        return period_start, period_end

    @staticmethod
    def _incident_overlap_seconds(
        incident: Incident,
        period_start: datetime,
        period_end: datetime,
    ) -> int:
        started_at = ReportService._as_naive_utc(incident.started_at)
        resolved_at = (
            ReportService._as_naive_utc(incident.resolved_at)
            if incident.resolved_at is not None
            else None
        )
        end = resolved_at or min(datetime.utcnow(), period_end)
        start = max(started_at, period_start)
        bounded_end = min(end, period_end)
        return max(0, int((bounded_end - start).total_seconds()))

    @staticmethod
    def _as_naive_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        if seconds <= 0:
            return "0 min"
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes} min"

    @staticmethod
    def _format_latency(value: float | None) -> str:
        return f"{value:.2f} ms" if value is not None else "No data"

    @staticmethod
    def month_name(month: int) -> str:
        return calendar.month_name[month]
