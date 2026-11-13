from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TraceSpanIngest(BaseModel):
    """Native span format accepted alongside OTLP/JSON."""

    trace_id: str = Field(..., min_length=1, max_length=64)
    span_id: str = Field(..., min_length=1, max_length=64)
    parent_span_id: str | None = Field(None, max_length=64)
    service: str = Field(..., min_length=1, max_length=255)
    operation: str = Field(..., min_length=1, max_length=255)
    kind: str | None = Field(None, max_length=20)
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: float | None = Field(None, ge=0)
    status: str | None = Field(None, max_length=20)
    status_message: str | None = None
    attributes: dict[str, object] | None = None


class TraceIngestRequest(BaseModel):
    spans: list[TraceSpanIngest] = Field(..., min_length=1, max_length=2000)


class TraceIngestResponse(BaseModel):
    accepted: int


class TraceSpanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    kind: str | None
    start_time: datetime
    end_time: datetime | None
    duration_ms: float | None
    status: str
    status_message: str | None
    attributes: dict[str, object] | None


class TraceSpanList(BaseModel):
    spans: list[TraceSpanResponse]
    total: int


class TraceSummary(BaseModel):
    trace_id: str
    root_service: str | None
    root_operation: str | None
    span_count: int
    service_count: int
    error_count: int
    started_at: datetime
    duration_ms: float | None


class TraceList(BaseModel):
    traces: list[TraceSummary]
    total: int


class ServiceMapEdge(BaseModel):
    source: str
    target: str
    call_count: int
    avg_duration_ms: float | None
    error_count: int


class ServiceMapResponse(BaseModel):
    edges: list[ServiceMapEdge]
    services: list[str]
