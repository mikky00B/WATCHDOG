from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationChannelType(str, Enum):
    EMAIL = "EMAIL"
    TELEGRAM = "TELEGRAM"


class NotificationChannelCreate(BaseModel):
    organization_id: int | None = None
    name: str = Field(..., min_length=1, max_length=255)
    channel_type: NotificationChannelType
    config: dict[str, object]
    is_active: bool = True

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, object]) -> dict[str, object]:
        if not value:
            raise ValueError("config is required")
        return value


class NotificationChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    config: dict[str, object] | None = None
    is_active: bool | None = None


class NotificationChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None
    name: str
    channel_type: str
    config: dict[str, object]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationChannelList(BaseModel):
    channels: list[NotificationChannelResponse]
    total: int


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None
    monitor_id: int | None
    incident_id: int | None
    channel_id: int | None
    event_type: str
    status: str
    message: str
    error_message: str | None
    sent_at: datetime | None
    created_at: datetime

