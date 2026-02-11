from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MonitorBase(BaseModel):
    """Base monitor schema."""

    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    monitor_type: str = Field(default="http", max_length=50)
    interval_seconds: int = Field(ge=10, le=3600)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)


class MonitorCreate(MonitorBase):
    """Schema for creating a monitor."""

    pass


class MonitorUpdate(BaseModel):
    """Schema for updating a monitor."""

    name: str | None = Field(None, min_length=1, max_length=255)
    url: HttpUrl | None = None
    monitor_type: str | None = Field(None, max_length=50)
    interval_seconds: int | None = Field(None, ge=10, le=3600)
    timeout_seconds: float | None = Field(None, ge=1.0, le=60.0)
    enabled: bool | None = None


class MonitorResponse(MonitorBase):
    """Schema for monitor response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MonitorList(BaseModel):
    """Schema for list of monitors."""

    monitors: list[MonitorResponse]
    total: int
