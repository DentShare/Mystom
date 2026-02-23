"""Простой per-user rate limiting middleware."""
import time
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery


class ThrottleMiddleware(BaseMiddleware):
    """Ограничивает количество запросов от пользователя: не более rate за period секунд."""

    def __init__(self, rate: int = 5, period: float = 10.0):
        self._rate = rate
        self._period = period
        self._timestamps: Dict[int, list] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        timestamps = self._timestamps[user_id]
        # Убираем устаревшие метки
        cutoff = now - self._period
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self._rate:
            if isinstance(event, Message):
                await event.answer("⏳ Слишком много запросов. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Подождите немного.", show_alert=False)
            return

        timestamps.append(now)
        return await handler(event, data)
