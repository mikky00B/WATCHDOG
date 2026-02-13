"""Minimal Telegram webhook schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat: TelegramChat
    text: str | None = None
    message_id: int | None = None


class TelegramCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    data: str | None = None
    message: TelegramMessage | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None
