from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.config import Settings, get_settings
from monitoring.core.security import decode_access_token
from monitoring.database import get_db
from monitoring.models.api_key import ApiKey
from monitoring.models.user import User
from monitoring.services.api_key_service import ApiKeyService
from monitoring.services.auth_service import AuthService
from monitoring.services.telegram_service import TelegramService

# Type alias for database dependency
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = await AuthService(db).get_user_by_public_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    if authorization is None:
        return None
    try:
        return await get_current_user(db, authorization)
    except HTTPException:
        return None


OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


def get_telegram_service(
    db: DbSession,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> TelegramService | None:
    """Dependency to get Telegram service."""
    if (
        settings.telegram_bot_token is None
        or not settings.telegram_allowed_chat_ids
    ):
        return None

    return TelegramService(
        db=db,
        bot_token=settings.telegram_bot_token,
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
    )


TelegramServiceDep = Annotated[TelegramService | None, Depends(get_telegram_service)]


async def get_api_key_auth(
    db: DbSession,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiKey:
    """Authenticate a machine client via API key (X-API-Key or Bearer token)."""
    raw_key = x_api_key
    if raw_key is None and authorization is not None:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].startswith("wd_"):
            raw_key = parts[1]

    if raw_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required (X-API-Key header)",
        )

    api_key = await ApiKeyService(db).authenticate(raw_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked API key",
        )
    await ApiKeyService(db).mark_used(api_key)
    return api_key


ApiKeyAuth = Annotated[ApiKey, Depends(get_api_key_auth)]


def require_api_key_scope(scope: str):
    """Dependency factory: require the API key to include a specific scope.

    Keys with no scopes configured have full ingestion access.
    """

    async def _check(api_key: ApiKeyAuth) -> ApiKey:
        permissions = api_key.permissions or {}
        scopes = permissions.get("scopes") if isinstance(permissions, dict) else None
        if isinstance(scopes, list) and scopes and scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key is missing required scope '{scope}'",
            )
        return api_key

    return _check
