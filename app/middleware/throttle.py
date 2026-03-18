"""Per-user rate limiting middleware с поддержкой Redis (fallback на in-memory)."""
import logging
import time
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)

# Глобальный Redis-клиент (инициализируется при старте, если REDIS_URL задан)
_redis_client = None


async def init_redis(redis_url: str) -> bool:
    """Попытка подключения к Redis. Возвращает True при успехе."""
    global _redis_client
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        await client.ping()
        _redis_client = client
        logger.info("Redis rate-limiter подключён: %s", redis_url.split("@")[-1] if "@" in redis_url else redis_url)
        return True
    except ImportError:
        logger.info("redis пакет не установлен — rate limiting in-memory")
        return False
    except Exception as e:
        logger.warning("Redis недоступен (%s) — rate limiting in-memory", e)
        return False


async def close_redis() -> None:
    """Закрытие Redis-соединения."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


class ThrottleMiddleware(BaseMiddleware):
    """Ограничивает количество запросов от пользователя: не более rate за period секунд.

    Если Redis доступен — использует sorted sets (персистентный, масштабируемый).
    Иначе — in-memory defaultdict (как раньше).
    """

    def __init__(self, rate: int = 5, period: float = 10.0, key_prefix: str = "throttle"):
        self._rate = rate
        self._period = period
        self._key_prefix = key_prefix
        # In-memory fallback
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

        if _redis_client:
            is_limited = await self._check_redis(user_id)
        else:
            is_limited = self._check_memory(user_id)

        if is_limited:
            if isinstance(event, Message):
                await event.answer("⏳ Слишком много запросов. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Подождите немного.", show_alert=False)
            return

        return await handler(event, data)

    def _check_memory(self, user_id: int) -> bool:
        """In-memory rate check (fallback)."""
        now = time.monotonic()
        timestamps = self._timestamps[user_id]
        cutoff = now - self._period
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self._rate:
            return True

        timestamps.append(now)
        return False

    async def _check_redis(self, user_id: int) -> bool:
        """Redis-based rate check с sorted set (sliding window)."""
        try:
            key = f"{self._key_prefix}:{user_id}"
            now = time.time()
            cutoff = now - self._period

            pipe = _redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)  # убрать старые
            pipe.zcard(key)  # текущее кол-во
            pipe.zadd(key, {str(now): now})  # добавить текущий
            pipe.expire(key, int(self._period) + 1)  # TTL
            results = await pipe.execute()

            count = results[1]  # zcard до добавления
            if count >= self._rate:
                # Убираем только что добавленный
                await _redis_client.zrem(key, str(now))
                return True
            return False
        except Exception as e:
            logger.warning("Redis throttle error, fallback to memory: %s", e)
            return self._check_memory(user_id)
