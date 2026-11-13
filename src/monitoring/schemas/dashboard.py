from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

VALID_WIDGET_TYPES = {
    "monitor_status",
    "uptime",
    "response_times",
    "log_volume",
    "host_health",
    "incidents",
    "service_map",
    "slo_status",
}


class WidgetConfig(BaseModel):
    type: str
    title: str = Field(default="", max_length=255)
    config: dict[str, object] = Field(default_factory=dict)


class DashboardTemplateCreate(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    widgets: list[WidgetConfig] = Field(default_factory=list)
    is_default: bool = False


class DashboardTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    widgets: list[WidgetConfig] | None = None
    is_default: bool | None = None


class DashboardTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    widgets: list[object] | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class DashboardTemplateList(BaseModel):
    dashboards: list[DashboardTemplateResponse]
    total: int
