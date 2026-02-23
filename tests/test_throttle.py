"""Тесты для app.middleware.throttle."""
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from app.middleware.throttle import ThrottleMiddleware


def _make_message_event(user_id: int):
    """Создать мок Message с from_user.id."""
    from aiogram.types import Message
    event = MagicMock(spec=Message)
    event.from_user = MagicMock()
    event.from_user.id = user_id
    event.answer = AsyncMock()
    # isinstance check needs to work
    type(event).__class__ = Message
    return event


@pytest.mark.asyncio
async def test_allows_under_rate_limit():
    """Запросы в пределах лимита проходят."""
    mw = ThrottleMiddleware(rate=3, period=10)
    handler = AsyncMock()

    from aiogram.types import Message
    for _ in range(3):
        event = MagicMock(spec=Message)
        event.from_user = MagicMock(id=123)
        event.answer = AsyncMock()
        # Force isinstance to return True for Message
        await mw(handler, event, {})

    assert handler.call_count == 3


@pytest.mark.asyncio
async def test_blocks_over_rate_limit():
    """Запросы сверх лимита блокируются."""
    mw = ThrottleMiddleware(rate=2, period=60)
    handler = AsyncMock()

    from aiogram.types import Message
    for _ in range(4):
        event = MagicMock(spec=Message)
        event.from_user = MagicMock(id=456)
        event.answer = AsyncMock()
        await mw(handler, event, {})

    # Только 2 первых должны пройти
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_different_users_independent():
    """Лимиты независимы для разных пользователей."""
    mw = ThrottleMiddleware(rate=1, period=60)
    handler = AsyncMock()

    from aiogram.types import Message
    for uid in [100, 200, 300]:
        event = MagicMock(spec=Message)
        event.from_user = MagicMock(id=uid)
        event.answer = AsyncMock()
        await mw(handler, event, {})

    assert handler.call_count == 3


@pytest.mark.asyncio
async def test_no_user_passes_through():
    """Событие без from_user проходит без лимита."""
    mw = ThrottleMiddleware(rate=1, period=60)
    handler = AsyncMock()

    event = MagicMock()
    event.from_user = None
    await mw(handler, event, {})
    await mw(handler, event, {})

    assert handler.call_count == 2
