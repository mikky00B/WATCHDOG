"""Telegram integration webhook router."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Response

from monitoring.config import Settings, get_settings
from monitoring.dependencies import TelegramServiceDep
from monitoring.schemas.telegram import TelegramUpdate

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/webhook", status_code=200)
async def telegram_webhook(
    update: TelegramUpdate,
    service: TelegramServiceDep,
    settings: Settings = Depends(get_settings),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    """Receive Telegram webhook updates and delegate handling to the service."""
    if service is None:
        logger.warning("telegram_webhook_called_while_disabled")
        raise HTTPException(status_code=503, detail="Telegram integration is disabled")

    webhook_secret = settings.telegram_webhook_secret
    if not webhook_secret or x_telegram_bot_api_secret_token != webhook_secret:
        logger.warning("telegram_webhook_secret_mismatch")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    await service.handle_update(update)
    return Response(status_code=200)

