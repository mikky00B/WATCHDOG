from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HeartbeatBase(BaseModel):
    """Base heartbeat schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    expected_interval_seconds: int = Field(ge=10, le=86400)


class HeartbeatCreate(HeartbeatBase):
    """Schema for creating a heartbeat."""

    pass


class HeartbeatUpdate(BaseModel):
    """Schema for updating a heartbeat."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    expected_interval_seconds: int | None = Field(None, ge=10, le=86400)


class HeartbeatResponse(HeartbeatBase):
    """Schema for heartbeat response."""

    model_config = ConfigDict(from_attributes=True)

    public_id: uuid.UUID
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HeartbeatPing(BaseModel):
    """Schema for heartbeat ping."""

    public_id: uuid.UUID


class HeartbeatList(BaseModel):
    """Schema for list of heartbeats."""

    heartbeats: list[HeartbeatResponse]
    total: int
