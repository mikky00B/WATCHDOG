from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StatusPageCreate(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    logo_url: HttpUrl | None = None
    brand_color: str | None = Field(None, max_length=32)
    is_active: bool = True


class StatusPageUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    logo_url: HttpUrl | None = None
    brand_color: str | None = Field(None, max_length=32)
    is_active: bool | None = None


class StatusPageServiceCreate(BaseModel):
    monitor_id: uuid.UUID
    display_name: str = Field(..., min_length=1, max_length=255)
    sort_order: int = Field(default=0, ge=0)
    is_visible: bool = True


class StatusPageServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    status_page_id: int
    monitor_id: int
    display_name: str
    sort_order: int
    is_visible: bool


class StatusPageServiceList(BaseModel):
    services: list[StatusPageServiceResponse]
    total: int


class StatusPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    organization_id: int
    name: str
    slug: str
    logo_url: str | None
    brand_color: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StatusPageList(BaseModel):
    status_pages: list[StatusPageResponse]
    total: int


class PublicStatusService(BaseModel):
    id: int
    display_name: str
    status: str
    uptime_30d: float


class PublicStatusPageResponse(BaseModel):
    name: str
    slug: str
    logo_url: str | None
    brand_color: str | None
    overall_status: str
    services: list[PublicStatusService]
    active_incidents: list[dict[str, object]]
    recent_incidents: list[dict[str, object]]
    maintenance_windows: list[dict[str, object]]
