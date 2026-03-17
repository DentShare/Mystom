"""Тесты сервиса мониторинга ошибок."""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.error_monitor import ErrorMonitor, _error_key, _truncate


class TestTruncate:

    def test_short_text(self):
        assert _truncate("hello", 100) == "hello"

    def test_long_text(self):
        result = _truncate("x" * 5000, 100)
        assert len(result) <= 100
        assert "обрезано" in result


class TestErrorKey:

    def test_generates_key(self):
        try:
            raise ValueError("test")
        except ValueError as e:
            key = _error_key(e)
            assert "ValueError@" in key
            assert "test_error_monitor.py" in key


class TestErrorMonitor:

    @pytest.mark.asyncio
    async def test_start_stop(self):
        monitor = ErrorMonitor()
        bot = AsyncMock()
        await monitor.start(bot)
        assert monitor._bot is bot
        assert monitor._started_at is not None
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_report_sends_to_admins(self):
        monitor = ErrorMonitor()
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        monitor._bot = bot

        with patch("app.services.error_monitor.Config") as mock_config:
            mock_config.ADMIN_IDS = [111, 222]
            try:
                raise RuntimeError("test error")
            except RuntimeError as e:
                await monitor.report(e, context="unit test", user_id=42)

        assert bot.send_message.call_count == 2
        # Проверяем что ошибка упомянута в сообщении
        call_text = bot.send_message.call_args_list[0][1].get("text", "") or bot.send_message.call_args_list[0][0][1]
        assert "RuntimeError" in call_text

    @pytest.mark.asyncio
    async def test_dedup_suppresses_same_error(self):
        monitor = ErrorMonitor()
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        monitor._bot = bot

        with patch("app.services.error_monitor.Config") as mock_config:
            mock_config.ADMIN_IDS = [111]

            def raise_and_report():
                try:
                    raise ValueError("same error")
                except ValueError as e:
                    return e

            e1 = raise_and_report()
            e2 = raise_and_report()

            await monitor.report(e1)
            await monitor.report(e2)  # дубль — подавится

        # Отправлено только 1 раз (дубль подавлен)
        assert bot.send_message.call_count == 1
        assert monitor._suppressed  # есть подавленные

    @pytest.mark.asyncio
    async def test_get_stats(self):
        monitor = ErrorMonitor()
        bot = AsyncMock()
        await monitor.start(bot)
        stats = await monitor.get_stats()
        assert "Мониторинг ошибок" in stats
        assert "Аптайм" in stats
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_report_warning(self):
        monitor = ErrorMonitor()
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        monitor._bot = bot

        with patch("app.services.error_monitor.Config") as mock_config:
            mock_config.ADMIN_IDS = [111]
            await monitor.report_warning("Тестовое предупреждение")

        assert bot.send_message.call_count == 1
        call_text = bot.send_message.call_args_list[0][1].get("text", "") or bot.send_message.call_args_list[0][0][1]
        assert "Предупреждение" in call_text
