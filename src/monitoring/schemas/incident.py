from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentCreate(BaseModel):
    monitor_id: int
    organization_id: int | None = None
    title: str = Field(..., max_length=500)
    severity: IncidentSeverity = IncidentSeverity.HIGH
    reason: str
    started_at: datetime


class IncidentUpdateCreate(BaseModel):
    message: str = Field(..., min_length=1)
    visibility: str = Field(default="INTERNAL", max_length=50)


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None
    monitor_id: int
    title: str
    status: str
    severity: str
    reason: str
    started_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: int | None
    resolved_at: datetime | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime


class IncidentUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    user_id: int | None
    message: str
    visibility: str
    created_at: datetime


class IncidentList(BaseModel):
    incidents: list[IncidentResponse]
    total: int

