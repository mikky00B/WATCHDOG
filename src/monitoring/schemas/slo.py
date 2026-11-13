from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SLOCreate(BaseModel):
    organization_id: uuid.UUID
    monitor_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    target_percentage: float = Field(..., ge=50, le=100)
    window_days: int = Field(default=30, ge=1, le=365)


class SLOUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    target_percentage: float | None = Field(None, ge=50, le=100)
    window_days: int | None = Field(None, ge=1, le=365)


class SLOResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: int | None = None
    name: str
    description: str | None
    target_percentage: float
    window_days: int
    created_at: datetime
    updated_at: datetime


class SLOList(BaseModel):
    slos: list[SLOResponse]
    total: int


class SLOStatus(BaseModel):
    """Computed SLO attainment and error budget for one objective."""

    slo_id: uuid.UUID
    name: str
    monitor_public_id: uuid.UUID
    monitor_name: str
    target_percentage: float
    window_days: int
    period_start: datetime
    period_end: datetime
    total_checks: int
    successful_checks: int
    attained_percentage: float
    target_met: bool
    error_budget_minutes: float
    error_budget_used_minutes: float
    error_budget_remaining_percentage: float
