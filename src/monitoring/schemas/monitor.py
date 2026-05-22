from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class MonitorBase(BaseModel):
    """Base monitor schema."""

    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl | None = None
    monitor_type: str = Field(default="http", max_length=50)
    http_method: str = Field(default="GET", max_length=20)
    expected_status_code: int | None = Field(None, ge=100, le=599)
    expected_response_text: str | None = None
    expected_json: dict[str, object] | None = None
    request_headers: dict[str, str] | None = None
    request_body: str | None = None
    interval_seconds: int = Field(ge=10, le=3600)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    response_time_threshold_ms: int | None = Field(None, ge=1)
    enabled: bool = Field(default=True)

    @field_validator("monitor_type")
    @classmethod
    def normalize_monitor_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized == "HTTP":
            return "WEBSITE"
        if normalized not in {"WEBSITE", "API", "HEARTBEAT", "SSL"}:
            raise ValueError("monitor_type must be WEBSITE, API, HEARTBEAT, or SSL")
        return normalized

    @field_validator("http_method")
    @classmethod
    def normalize_http_method(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            raise ValueError("Unsupported HTTP method")
        return normalized

    @model_validator(mode="after")
    def validate_target_url(self) -> MonitorBase:
        if self.monitor_type != "HEARTBEAT" and self.url is None:
            raise ValueError("url is required for WEBSITE, API, and SSL monitors")
        return self


class MonitorCreate(MonitorBase):
    """Schema for creating a monitor."""

    organization_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None


class MonitorUpdate(BaseModel):
    """Schema for updating a monitor."""

    name: str | None = Field(None, min_length=1, max_length=255)
    url: HttpUrl | None = None
    monitor_type: str | None = Field(None, max_length=50)
    http_method: str | None = Field(None, max_length=20)
    expected_status_code: int | None = Field(None, ge=100, le=599)
    expected_response_text: str | None = None
    expected_json: dict[str, object] | None = None
    request_headers: dict[str, str] | None = None
    request_body: str | None = None
    interval_seconds: int | None = Field(None, ge=10, le=3600)
    timeout_seconds: float | None = Field(None, ge=1.0, le=60.0)
    response_time_threshold_ms: int | None = Field(None, ge=1)
    enabled: bool | None = None


class MonitorResponse(MonitorBase):
    """Schema for monitor response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    client_id: int | None = None
    heartbeat_key: str | None = None
    heartbeat_url: str | None = None
    status: str = "UNKNOWN"
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_checked_at: datetime | None
    next_check_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MonitorList(BaseModel):
    """Schema for list of monitors."""

    monitors: list[MonitorResponse]
    total: int


class MonitorStats(BaseModel):
    """Aggregated check statistics for one monitor."""

    monitor_id: int
    total_checks: int
    successful_checks: int
    failed_checks: int
    uptime_percentage: float
    average_latency_ms: float | None
    last_checked_at: datetime | None
    last_status_code: int | None
    last_error_message: str | None
