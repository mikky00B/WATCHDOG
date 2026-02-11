from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckResultBase(BaseModel):
    """Base check result schema."""

    status_code: int | None = None
    latency_ms: float | None = None
    success: bool
    error_message: str | None = Field(None, max_length=1000)


class CheckResultCreate(CheckResultBase):
    """Schema for creating a check result."""

    monitor_id: int


class CheckResultResponse(CheckResultBase):
    """Schema for check result response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    checked_at: datetime


class CheckResultList(BaseModel):
    """Schema for list of check results."""

    results: list[CheckResultResponse]
    total: int
