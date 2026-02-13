from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.database import get_db
from monitoring.services.telegram_service import TelegramService
from monitoring.config import get_settings, Settings

# Type alias for database dependency
DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_telegram_service(
    db: DbSession,
    settings: Settings = Depends(get_settings),
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
