from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

API_KEY_SCOPES = {"logs:write", "metrics:write", "traces:write", "heartbeat:write"}


class ApiKeyCreate(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)

    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> None:
        invalid = [scope for scope in scopes if scope not in API_KEY_SCOPES]
        if invalid:
            raise ValueError("Unknown scopes: " + ", ".join(invalid))


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    permissions: dict[str, object] | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Includes the raw key — returned exactly once, at creation time."""

    key: str


class ApiKeyList(BaseModel):
    api_keys: list[ApiKeyResponse]
    total: int
