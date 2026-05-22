from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    name: str
    slug: str
    owner_id: int
    created_at: datetime
    updated_at: datetime


class OrganizationList(BaseModel):
    organizations: list[OrganizationResponse]
    total: int

