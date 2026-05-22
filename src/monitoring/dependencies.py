from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.config import Settings, get_settings
from monitoring.core.security import decode_access_token
from monitoring.database import get_db
from monitoring.models.user import User
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
