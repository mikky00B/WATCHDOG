from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.api_key import ApiKey
from monitoring.schemas.api_key import API_KEY_SCOPES, ApiKeyCreate

logger = structlog.get_logger(__name__)

API_KEY_PREFIX = "wd_live_"
_RAW_KEY_LENGTH = 32  # urlsafe bytes -> ~43 chars


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKeyService:
    """Business logic for organization API keys."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(
        self,
        organization_id: int,
        data: ApiKeyCreate,
    ) -> tuple[ApiKey, str]:
        """Create an API key. Returns (record, raw_key) — the raw key is shown once."""
        invalid = [scope for scope in data.scopes if scope not in API_KEY_SCOPES]
        if invalid:
            raise ValueError(f"Unknown scopes: {', '.join(invalid)}")

        raw_key = API_KEY_PREFIX + secrets.token_urlsafe(_RAW_KEY_LENGTH)
        api_key = ApiKey(
            organization_id=organization_id,
            name=data.name,
            key_prefix=raw_key[:16],
            key_hash=hash_api_key(raw_key),
            permissions={"scopes": data.scopes} if data.scopes else None,
            expires_at=data.expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)
        logger.info(
            "api_key_created",
            organization_id=organization_id,
            key_prefix=api_key.key_prefix,
        )
        return api_key, raw_key

    async def get_key(self, api_key_public_id: uuid.UUID) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.public_id == api_key_public_id),
        )
        return result.scalar_one_or_none()

    async def list_keys(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ApiKey], int]:
        base_stmt = select(ApiKey).where(ApiKey.organization_id == organization_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(ApiKey.created_at.desc()).offset(skip).limit(limit),
        )
        return list(result.scalars().all()), total

    async def revoke_key(self, api_key_public_id: uuid.UUID) -> ApiKey | None:
        api_key = await self.get_key(api_key_public_id)
        if api_key is None:
            return None
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(api_key)
        return api_key

    async def authenticate(self, raw_key: str) -> ApiKey | None:
        """Resolve an API key by its raw value; returns None if unknown/expired/revoked."""
        if not raw_key:
            return None
        key_hash = hash_api_key(raw_key)
        api_key = (
            await self.db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        ).scalar_one_or_none()
        if api_key is None:
            return None
        if api_key.revoked_at is not None:
            return None
        if api_key.expires_at is not None:
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None
        return api_key

    async def mark_used(self, api_key: ApiKey) -> None:
        api_key.last_used_at = datetime.now(UTC)
        await self.db.flush()
