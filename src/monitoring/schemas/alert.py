from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertBase(BaseModel):
    """Base alert schema."""

    severity: AlertSeverity
    title: str = Field(..., max_length=500)
    message: str


class AlertCreate(AlertBase):
    """Schema for creating an alert."""

    monitor_id: int
    triggered_at: datetime


class AlertUpdate(BaseModel):
    """Schema for updating an alert."""

    resolved: bool | None = None
    acknowledged: bool | None = None
    resolved_at: datetime | None = None


class AlertResponse(AlertBase):
    """Schema for alert response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    resolved: bool
    acknowledged: bool
    triggered_at: datetime
    resolved_at: datetime | None
    created_at: datetime


class AlertList(BaseModel):
    """Schema for list of alerts."""

    alerts: list[AlertResponse]
    total: int
