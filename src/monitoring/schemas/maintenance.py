from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MaintenanceWindowBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    notify_subscribers: bool = False

    @model_validator(mode="after")
    def validate_period(self) -> MaintenanceWindowBase:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class MaintenanceWindowCreate(MaintenanceWindowBase):
    organization_id: uuid.UUID
    monitor_ids: list[uuid.UUID] = Field(default_factory=list)


class MaintenanceWindowUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notify_subscribers: bool | None = None
    monitor_ids: list[uuid.UUID] | None = None


class MaintenanceWindowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: int | None = None
    title: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    notify_subscribers: bool
    monitor_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MaintenanceWindowList(BaseModel):
    windows: list[MaintenanceWindowResponse]
    total: int
