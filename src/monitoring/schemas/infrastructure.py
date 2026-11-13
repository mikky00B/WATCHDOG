from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HostMetricIngest(BaseModel):
    """Metrics payload sent by the WATCHDOG infrastructure agent."""

    host: str = Field(..., min_length=1, max_length=255)
    timestamp: datetime | None = None
    environment: str | None = Field(None, max_length=50)
    cpu_percent: float | None = Field(None, ge=0, le=100)
    memory_percent: float | None = Field(None, ge=0, le=100)
    memory_used_mb: float | None = Field(None, ge=0)
    disk_percent: float | None = Field(None, ge=0, le=100)
    disk_used_gb: float | None = Field(None, ge=0)
    net_in_kb_per_s: float | None = Field(None, ge=0)
    net_out_kb_per_s: float | None = Field(None, ge=0)
    processes: list[dict[str, object]] | None = None
    service_checks: dict[str, bool] | None = None


class InfraIngestRequest(BaseModel):
    metrics: list[HostMetricIngest] = Field(..., min_length=1, max_length=100)


class InfraIngestResponse(BaseModel):
    accepted: int


class HostThresholdCreate(BaseModel):
    organization_id: uuid.UUID
    host: str = Field(..., min_length=1, max_length=255)
    cpu_percent: float | None = Field(None, ge=1, le=100)
    memory_percent: float | None = Field(None, ge=1, le=100)
    disk_percent: float | None = Field(None, ge=1, le=100)
    process_names: list[str] | None = None

    @model_validator(mode="after")
    def validate_has_threshold(self) -> HostThresholdCreate:
        if (
            self.cpu_percent is None
            and self.memory_percent is None
            and self.disk_percent is None
            and not self.process_names
        ):
            raise ValueError("At least one threshold or process name must be set")
        return self


class HostThresholdUpdate(BaseModel):
    cpu_percent: float | None = Field(None, ge=1, le=100)
    memory_percent: float | None = Field(None, ge=1, le=100)
    disk_percent: float | None = Field(None, ge=1, le=100)
    process_names: list[str] | None = None
    enabled: bool | None = None


class HostThresholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host: str
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    process_names: list[object] | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class HostThresholdList(BaseModel):
    thresholds: list[HostThresholdResponse]
    total: int


class HostMetricSample(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    host: str
    environment: str | None
    cpu_percent: float | None
    memory_percent: float | None
    memory_used_mb: float | None
    disk_percent: float | None
    disk_used_gb: float | None
    net_in_kb_per_s: float | None
    net_out_kb_per_s: float | None
    processes: list[object] | None
    service_checks: dict[str, object] | None
    measured_at: datetime


class HostSummary(BaseModel):
    """Latest known state of one host plus recent samples for charting."""

    host: str
    environment: str | None = None
    latest: HostMetricSample | None = None
    history: list[HostMetricSample] = Field(default_factory=list)
    threshold: HostThresholdResponse | None = None
    health: str = "UNKNOWN"  # OK | WARNING | CRITICAL | UNKNOWN


class InfraSummary(BaseModel):
    hosts: list[HostSummary]
    total_hosts: int
