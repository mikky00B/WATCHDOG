from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.schemas.telegram import TelegramCallbackQuery, TelegramMessage, TelegramUpdate
from monitoring.services.telegram_service import TelegramService


@pytest.mark.unit
async def test_telegram_command_routing(test_db: AsyncSession) -> None:
    service = TelegramService(test_db, "bot-token", ["123"])
    service._send_message = AsyncMock()
    service._handle_status = AsyncMock()
    service._handle_monitors = AsyncMock()
    service._handle_alerts = AsyncMock()
    service._handle_ack = AsyncMock()
    service._handle_resolve = AsyncMock()
    service._handle_enable = AsyncMock()
    service._handle_disable = AsyncMock()

    for command, handler in [
        ("/status", service._handle_status),
        ("/monitors", service._handle_monitors),
        ("/alerts", service._handle_alerts),
        ("/ack 1", service._handle_ack),
        ("/resolve 1", service._handle_resolve),
        ("/enable 1", service._handle_enable),
        ("/disable 1", service._handle_disable),
    ]:
        await service.handle_update(
            TelegramUpdate(message=TelegramMessage(chat={"id": 123}, text=command))
        )
        assert handler.await_count == 1

    await service.handle_update(
        TelegramUpdate(message=TelegramMessage(chat={"id": 999}, text="/status"))
    )
    await service.handle_update(
        TelegramUpdate(message=TelegramMessage(chat={"id": 123}, text="/unknown"))
    )
    service._send_message.assert_awaited()


@pytest.mark.unit
async def test_telegram_callbacks_and_helpers(test_db: AsyncSession) -> None:
    service = TelegramService(test_db, "bot-token", ["123"])
    service._send_message = AsyncMock()
    service._edit_message = AsyncMock()
    service._answer_callback_query = AsyncMock()
    service._execute_ack = AsyncMock(return_value=(True, "acknowledged"))
    service._execute_resolve = AsyncMock(return_value=(False, "not found"))

    await service.handle_update(
        TelegramUpdate(
            callback_query=TelegramCallbackQuery(
                id="cb1",
                data="ack:5",
                message=TelegramMessage(chat={"id": 123}, message_id=9),
            )
        )
    )
    await service.handle_update(
        TelegramUpdate(
            callback_query=TelegramCallbackQuery(
                id="cb2",
                data="resolve:5",
                message=TelegramMessage(chat={"id": 123}, message_id=None),
            )
        )
    )
    await service.handle_update(
        TelegramUpdate(
            callback_query=TelegramCallbackQuery(
                id="cb3",
                data="bad",
                message=TelegramMessage(chat={"id": 123}, message_id=1),
            )
        )
    )
    await service.handle_update(
        TelegramUpdate(
            callback_query=TelegramCallbackQuery(
                id="cb4",
                data="ack:5",
                message=TelegramMessage(chat={"id": 999}, message_id=1),
            )
        )
    )

    assert service._edit_message.await_count == 1
    assert service._answer_callback_query.await_count >= 2
    assert service._is_authorized("123")
    assert not service._is_authorized("999")
    assert service._parse_positive_int("5") == 5
    assert service._parse_positive_int("0") is None
    assert service._parse_positive_int("bad") is None
    assert "/status" in service._usage_text()


@pytest.mark.unit
async def test_telegram_handlers_cover_empty_and_enabled_paths(test_db: AsyncSession) -> None:
    service = TelegramService(test_db, "bot-token", ["123"])
    service._send_message = AsyncMock()
    service.monitor_service.list_monitors = AsyncMock(return_value=([], 0))
    service.alert_service.list_alerts = AsyncMock(return_value=([], 0))

    await service._handle_status("123")
    await service._handle_monitors("123")
    await service._handle_alerts("123")
    await service._handle_ack("123", [])
    await service._handle_resolve("123", ["1", "2"])
    await service._handle_enable("123", ["bad"])
    await service._handle_disable("123", ["bad"])

    service.monitor_service.list_monitors = AsyncMock(
        return_value=([SimpleNamespace(id=1, name="API", enabled=True)], 1)
    )
    service._latest_monitor_status = AsyncMock(return_value={1: True})
    await service._handle_monitors("123")

    service.monitor_service.get_monitor_by_internal_id = AsyncMock(return_value=None)
    await service._handle_enable("123", ["1"])
    await service._handle_disable("123", ["1"])
    assert service._send_message.await_count >= 9
