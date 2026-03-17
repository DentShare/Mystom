"""
Мониторинг ошибок: перехват, группировка, отправка отчётов админам в Telegram.

Использование:
    from app.services.error_monitor import error_monitor

    # Инициализация при старте бота
    await error_monitor.start(bot)

    # Отправка ошибки вручную (автоматически — через global_error_handler)
    await error_monitor.report(exception, context="описание")

    # Остановка при shutdown
    await error_monitor.stop()
"""
import asyncio
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot

from app.config import Config

logger = logging.getLogger(__name__)

# Максимальная длина сообщения Telegram
_MAX_MSG_LEN = 4000
# Минимальный интервал между одинаковыми ошибками (антиспам)
_DEDUP_SECONDS = 300  # 5 минут
# Интервал дайджеста (сводка подавленных ошибок)
_DIGEST_INTERVAL = 3600  # 1 час


def _truncate(text: str, max_len: int = _MAX_MSG_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n\n… (обрезано)"


def _error_key(exc: BaseException) -> str:
    """Ключ для группировки одинаковых ошибок: тип + место возникновения."""
    tb = traceback.extract_tb(exc.__traceback__)
    location = f"{tb[-1].filename}:{tb[-1].lineno}" if tb else "unknown"
    return f"{type(exc).__name__}@{location}"


class ErrorMonitor:
    """Центральный сервис мониторинга ошибок."""

    def __init__(self):
        self._bot: Optional[Bot] = None
        self._recent: dict[str, datetime] = {}  # key → last_sent_at
        self._suppressed: defaultdict[str, int] = defaultdict(int)  # key → count
        self._digest_task: Optional[asyncio.Task] = None
        self._total_errors = 0
        self._started_at: Optional[datetime] = None

    async def start(self, bot: Bot) -> None:
        """Инициализация: запоминаем бота и стартуем дайджест."""
        self._bot = bot
        self._started_at = datetime.now()
        self._digest_task = asyncio.create_task(self._digest_loop())
        logger.info("ErrorMonitor запущен, отчёты → ADMIN_IDS=%s", Config.ADMIN_IDS)

    async def stop(self) -> None:
        """Остановка дайджеста."""
        if self._digest_task:
            self._digest_task.cancel()
            try:
                await self._digest_task
            except asyncio.CancelledError:
                pass
        # Отправить финальный дайджест если есть подавленные
        await self._send_digest()

    async def report(
        self,
        exc: BaseException,
        context: str = "",
        user_id: Optional[int] = None,
        handler: str = "",
    ) -> None:
        """
        Отчёт об ошибке. Дедупликация: одна и та же ошибка не спамит чаще раз в 5 мин.
        Подавленные ошибки отправляются в дайджесте.
        """
        self._total_errors += 1
        key = _error_key(exc)
        now = datetime.now()

        # Антиспам: проверяем, отправляли ли недавно такую же
        last_sent = self._recent.get(key)
        if last_sent and (now - last_sent).total_seconds() < _DEDUP_SECONDS:
            self._suppressed[key] += 1
            logger.warning(
                "ErrorMonitor: подавлено (дубль %d): %s — %s",
                self._suppressed[key], key, exc,
            )
            return

        self._recent[key] = now

        # Формируем отчёт
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        parts = [
            f"🚨 <b>Ошибка в боте</b>\n",
            f"<b>Тип:</b> <code>{type(exc).__name__}</code>",
            f"<b>Сообщение:</b> {str(exc)[:500]}",
        ]
        if handler:
            parts.append(f"<b>Обработчик:</b> {handler}")
        if user_id:
            parts.append(f"<b>Пользователь:</b> <code>{user_id}</code>")
        if context:
            parts.append(f"<b>Контекст:</b> {context}")
        parts.append(f"\n<b>Traceback:</b>\n<pre>{_truncate(tb_text, 2500)}</pre>")
        parts.append(f"\n🕐 {now.strftime('%d.%m.%Y %H:%M:%S')}")

        text = _truncate("\n".join(parts))
        await self._send_to_admins(text)

    async def report_warning(self, message: str) -> None:
        """Отправка предупреждения (не исключение, а важное событие)."""
        now = datetime.now()
        text = (
            f"⚠️ <b>Предупреждение</b>\n\n"
            f"{message}\n\n"
            f"🕐 {now.strftime('%d.%m.%Y %H:%M:%S')}"
        )
        await self._send_to_admins(_truncate(text))

    async def get_stats(self) -> str:
        """Статистика мониторинга."""
        uptime = datetime.now() - self._started_at if self._started_at else timedelta(0)
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        return (
            f"📊 <b>Мониторинг ошибок</b>\n\n"
            f"🕐 Аптайм: {hours}ч {minutes}м\n"
            f"🚨 Всего ошибок: {self._total_errors}\n"
            f"🔇 Подавлено (дубли): {sum(self._suppressed.values())}\n"
            f"📋 Уникальных типов: {len(self._recent)}"
        )

    async def _send_to_admins(self, text: str) -> None:
        """Отправка сообщения всем админам."""
        if not self._bot or not Config.ADMIN_IDS:
            logger.warning("ErrorMonitor: нет бота или ADMIN_IDS, отчёт не отправлен")
            return
        for admin_id in Config.ADMIN_IDS:
            try:
                await self._bot.send_message(
                    admin_id, text, parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning("ErrorMonitor: не удалось отправить admin=%s: %s", admin_id, e)

    async def _send_digest(self) -> None:
        """Сводка подавленных ошибок."""
        if not self._suppressed:
            return
        lines = ["📋 <b>Дайджест подавленных ошибок</b>\n"]
        for key, count in sorted(self._suppressed.items(), key=lambda x: -x[1]):
            lines.append(f"  • <code>{key}</code> — {count} раз")
        lines.append(f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        self._suppressed.clear()
        await self._send_to_admins(_truncate("\n".join(lines)))

    async def _digest_loop(self) -> None:
        """Периодическая отправка дайджеста подавленных ошибок."""
        while True:
            try:
                await asyncio.sleep(_DIGEST_INTERVAL)
                await self._send_digest()
                # Очистка старых ключей дедупликации
                now = datetime.now()
                expired = [
                    k for k, t in self._recent.items()
                    if (now - t).total_seconds() > _DEDUP_SECONDS * 2
                ]
                for k in expired:
                    del self._recent[k]
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("ErrorMonitor digest error: %s", e)


# Глобальный синглтон
error_monitor = ErrorMonitor()
