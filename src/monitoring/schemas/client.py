from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr | None = None
    logo_url: HttpUrl | None = None
    notes: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    contact_email: EmailStr | None = None
    logo_url: HttpUrl | None = None
    notes: str | None = None


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: uuid.UUID
    organization_id: int
    name: str
    contact_email: str | None
    logo_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ClientList(BaseModel):
    clients: list[ClientResponse]
    total: int
