from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_MONITOR_TYPES = {"WEBSITE", "API", "HEARTBEAT", "SSL", "DNS", "TCP"}
VALID_DNS_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "SRV", "PTR"}


class MonitorBase(BaseModel):
    """Base monitor schema."""

    name: str = Field(..., min_length=1, max_length=255)
    url: str | None = None
    monitor_type: str = Field(default="http", max_length=50, validate_default=True)
    http_method: str = Field(default="GET", max_length=20)
    expected_status_code: int | None = Field(None, ge=100, le=599)
    expected_response_text: str | None = None
    expected_json: dict[str, object] | None = None
    expected_headers: dict[str, str] | None = None
    request_headers: dict[str, str] | None = None
    request_body: str | None = None
    interval_seconds: int = Field(ge=10, le=3600)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    response_time_threshold_ms: int | None = Field(None, ge=1)
    enabled: bool = Field(default=True)
    environment: str | None = Field(None, max_length=50)
    tags: list[str] | None = None
    port: int | None = Field(None, ge=1, le=65535)
    record_type: str | None = Field(None, max_length=20)
    expected_values: list[object] | None = None
    ssl_expiry_threshold_days: int | None = Field(None, ge=1, le=365)

    @field_validator("monitor_type")
    @classmethod
    def normalize_monitor_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized == "HTTP":
            return "WEBSITE"
        if normalized not in VALID_MONITOR_TYPES:
            raise ValueError(
                "monitor_type must be one of " + ", ".join(sorted(VALID_MONITOR_TYPES))
            )
        return normalized

    @field_validator("http_method")
    @classmethod
    def normalize_http_method(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            raise ValueError("Unsupported HTTP method")
        return normalized

    @field_validator("record_type")
    @classmethod
    def normalize_record_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in VALID_DNS_RECORD_TYPES:
            raise ValueError(
                "record_type must be one of " + ", ".join(sorted(VALID_DNS_RECORD_TYPES))
            )
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = []
        for tag in value:
            cleaned = tag.strip()
            if not cleaned:
                continue
            if len(cleaned) > 50:
                raise ValueError("Each tag must be at most 50 characters")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized or None

    @model_validator(mode="after")
    def validate_target(self) -> MonitorBase:
        if self.monitor_type == "HEARTBEAT":
            return self
        if self.url is None:
            raise ValueError(
                "url is required for WEBSITE, API, SSL, DNS, and TCP monitors"
            )
        if self.monitor_type in {"WEBSITE", "API", "SSL"}:
            parsed = urlparse(str(self.url))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(
                    "url must be an http(s) URL for WEBSITE, API, and SSL monitors"
                )
        if self.monitor_type == "TCP" and self.port is None:
            raise ValueError("port is required for TCP monitors")
        if self.monitor_type == "DNS" and self.record_type is None:
            self.record_type = "A"
        return self


class MonitorCreate(MonitorBase):
    """Schema for creating a monitor."""

    organization_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None


class MonitorUpdate(BaseModel):
    """Schema for updating a monitor."""

    name: str | None = Field(None, min_length=1, max_length=255)
    url: str | None = None
    monitor_type: str | None = Field(None, max_length=50)
    http_method: str | None = Field(None, max_length=20)
    expected_status_code: int | None = Field(None, ge=100, le=599)
    expected_response_text: str | None = None
    expected_json: dict[str, object] | None = None
    expected_headers: dict[str, str] | None = None
    request_headers: dict[str, str] | None = None
    request_body: str | None = None
    interval_seconds: int | None = Field(None, ge=10, le=3600)
    timeout_seconds: float | None = Field(None, ge=1.0, le=60.0)
    response_time_threshold_ms: int | None = Field(None, ge=1)
    enabled: bool | None = None
    environment: str | None = Field(None, max_length=50)
    tags: list[str] | None = None
    port: int | None = Field(None, ge=1, le=65535)
    record_type: str | None = Field(None, max_length=20)
    expected_values: list[object] | None = None
    ssl_expiry_threshold_days: int | None = Field(None, ge=1, le=365)

    @field_validator("monitor_type")
    @classmethod
    def normalize_monitor_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized == "HTTP":
            return "WEBSITE"
        if normalized not in VALID_MONITOR_TYPES:
            raise ValueError(
                "monitor_type must be one of " + ", ".join(sorted(VALID_MONITOR_TYPES))
            )
        return normalized

    @field_validator("http_method")
    @classmethod
    def normalize_http_method(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            raise ValueError("Unsupported HTTP method")
        return normalized

    @field_validator("record_type")
    @classmethod
    def normalize_record_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in VALID_DNS_RECORD_TYPES:
            raise ValueError(
                "record_type must be one of " + ", ".join(sorted(VALID_DNS_RECORD_TYPES))
            )
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = []
        for tag in value:
            cleaned = tag.strip()
            if not cleaned:
                continue
            if len(cleaned) > 50:
                raise ValueError("Each tag must be at most 50 characters")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized or None


class MonitorResponse(BaseModel):
    """Schema for monitor responses.

    Deliberately standalone (not inheriting MonitorBase): response validation
    must not apply create-side field constraints, so legitimately stored values
    such as interval_seconds=86400 (daily SSL checks) serialize correctly.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    url: str | None = None
    monitor_type: str
    http_method: str | None = None
    expected_status_code: int | None = None
    expected_response_text: str | None = None
    expected_json: dict[str, object] | None = None
    expected_headers: dict[str, str] | None = None
    request_headers: dict[str, str] | None = None
    request_body: str | None = None
    interval_seconds: int
    timeout_seconds: float | None = None
    response_time_threshold_ms: int | None = None
    enabled: bool = True
    environment: str | None = None
    tags: list[str] | None = None
    port: int | None = None
    record_type: str | None = None
    expected_values: list[object] | None = None
    ssl_expiry_threshold_days: int | None = None

    id: int
    public_id: uuid.UUID
    client_id: int | None = None
    heartbeat_key: str | None = None
    heartbeat_url: str | None = None
    status: str = "UNKNOWN"
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    ssl_expires_at: datetime | None = None
    ssl_issuer: str | None = None
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
