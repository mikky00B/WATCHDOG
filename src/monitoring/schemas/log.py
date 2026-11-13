from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

MAX_LOG_MESSAGE_LENGTH = 8000
MAX_LOG_BATCH = 500


class LogEntryIngest(BaseModel):
    """A single application log line accepted by the ingestion API."""

    application: str = Field(..., min_length=1, max_length=255)
    level: str = Field(..., max_length=20)
    message: str = Field(..., min_length=1, max_length=MAX_LOG_MESSAGE_LENGTH)
    timestamp: datetime | None = None
    environment: str | None = Field(None, max_length=50)
    logger_name: str | None = Field(None, max_length=255)
    host: str | None = Field(None, max_length=255)
    trace_id: str | None = Field(None, max_length=64)
    span_id: str | None = Field(None, max_length=64)
    attributes: dict[str, object] | None = None

    def normalized_level(self) -> str:
        level = self.level.upper()
        if level in {"WARN"}:
            return "WARNING"
        if level in {"FATAL"}:
            return "CRITICAL"
        return level

    def is_valid_level(self) -> bool:
        return self.normalized_level() in VALID_LOG_LEVELS


class LogIngestRequest(BaseModel):
    logs: list[LogEntryIngest] = Field(..., min_length=1, max_length=MAX_LOG_BATCH)
    application: str | None = Field(None, max_length=255)
    environment: str | None = Field(None, max_length=50)


class LogIngestResponse(BaseModel):
    accepted: int
    rejected: int


class LogEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application: str
    environment: str | None = None
    level: str
    message: str
    logger_name: str | None = None
    host: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    attributes: dict[str, object] | None = None
    timestamp: datetime


class LogList(BaseModel):
    logs: list[LogEntryResponse]
    total: int


class LogVolumeBucket(BaseModel):
    bucket: datetime
    total: int
    error: int


class LogStatsResponse(BaseModel):
    total: int
    by_level: dict[str, int]
    error_count: int
    applications: int
    volume: list[LogVolumeBucket]
    errors_by_application: dict[str, int]


class LogRetentionUpdate(BaseModel):
    retention_days: int = Field(..., ge=1, le=3650)
