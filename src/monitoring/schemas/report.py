from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportMonitorSummary(BaseModel):
    """Per-monitor reliability summary for a report period."""

    monitor_id: uuid.UUID
    name: str
    monitor_type: str
    status: str
    total_checks: int
    successful_checks: int
    failed_checks: int
    uptime_percentage: float
    downtime_seconds: int
    incident_count: int
    average_response_time_ms: float | None


class ReportIncidentSummary(BaseModel):
    """Incident row included in client reliability reports."""

    id: int
    monitor_id: uuid.UUID
    monitor_name: str
    title: str
    status: str
    severity: str
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None


class MonthlyReportResponse(BaseModel):
    """Server-calculated monthly reliability report."""

    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    organization_name: str
    client_id: uuid.UUID | None
    client_name: str
    period_start: datetime
    period_end: datetime
    monitors_included: int
    uptime_percentage: float
    total_downtime_seconds: int
    incident_count: int
    average_response_time_ms: float | None
    monitors: list[ReportMonitorSummary]
    incidents: list[ReportIncidentSummary]
