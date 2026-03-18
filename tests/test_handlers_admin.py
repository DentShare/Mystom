"""Тесты хендлеров админки и меню."""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import User
from app.handlers.menu import cmd_menu
from app.utils.permissions import full_permissions
from tests.helpers import make_message, make_state


class TestMenuHandler:
    """Тесты главного меню."""

    @pytest.mark.asyncio
    async def test_menu_owner(self, db_session: AsyncSession, doctor: User):
        """Владелец видит своё имя и специализацию."""
        msg = make_message("/menu")
        state = make_state()
        await cmd_menu(msg, doctor, doctor, full_permissions(), state)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert doctor.full_name in text
        assert "Standard" in text  # tier=1
        assert msg.answer.call_args[1].get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_menu_assistant(self, db_session: AsyncSession, doctor: User):
        """Ассистент видит имя врача и своё."""
        assistant = User(
            telegram_id=444444,
            full_name="Ассистент Тестов",
            role="assistant",
            owner_id=doctor.id,
            registration_completed=True,
        )
        db_session.add(assistant)
        await db_session.commit()
        await db_session.refresh(assistant)

        msg = make_message("/menu")
        state = make_state()
        await cmd_menu(msg, assistant, doctor, full_permissions(), state)
        text = msg.answer.call_args[0][0]
        assert "ассистент" in text.lower()
        assert doctor.full_name in text

    @pytest.mark.asyncio
    async def test_menu_clears_state(self, db_session: AsyncSession, doctor: User):
        """Меню очищает FSM state."""
        msg = make_message("/menu")
        state = make_state()
        await state.update_data(some_key="some_value")
        await cmd_menu(msg, doctor, doctor, full_permissions(), state)
        data = await state.get_data()
        assert data == {}


class TestAdminCommands:
    """Тесты админских команд."""

    @pytest.mark.asyncio
    async def test_admin_non_admin_rejected(self, db_session: AsyncSession):
        """Не-админ не может использовать /admin."""
        from app.handlers.admin import cmd_admin
        msg = make_message("/admin", user_id=999999)
        with patch("app.handlers.admin.Config") as mock_config:
            mock_config.ADMIN_IDS = [111111]
            await cmd_admin(msg)
        msg.answer.assert_called_once()
        assert "запрещён" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_admin_access_granted(self, db_session: AsyncSession):
        """Админ получает доступ к панели."""
        from app.handlers.admin import cmd_admin
        msg = make_message("/admin", user_id=111111)
        with patch("app.handlers.admin.Config") as mock_config:
            mock_config.ADMIN_IDS = [111111]
            mock_config.ADMIN_WEBAPP_URL = ""
            await cmd_admin(msg)
        text = msg.answer.call_args[0][0]
        assert "админ" in text.lower()

    @pytest.mark.asyncio
    async def test_set_tier(self, db_session: AsyncSession, doctor: User):
        """Установка тарифа через /admin_set_tier."""
        from app.handlers.admin import cmd_set_tier
        msg = make_message(f"/admin_set_tier {doctor.telegram_id} 2", user_id=111111)
        with patch("app.handlers.admin.Config") as mock_config:
            mock_config.ADMIN_IDS = [111111]
            await cmd_set_tier(msg, db_session)

        await db_session.refresh(doctor)
        assert doctor.subscription_tier == 2

    @pytest.mark.asyncio
    async def test_set_tier_non_admin(self, db_session: AsyncSession, doctor: User):
        """Не-админ не может менять тарифы."""
        from app.handlers.admin import cmd_set_tier
        msg = make_message(f"/admin_set_tier {doctor.telegram_id} 2", user_id=999999)
        with patch("app.handlers.admin.Config") as mock_config:
            mock_config.ADMIN_IDS = [111111]
            await cmd_set_tier(msg, db_session)
        # Тариф не изменился
        await db_session.refresh(doctor)
        assert doctor.subscription_tier == 1

    @pytest.mark.asyncio
    async def test_list_users(self, db_session: AsyncSession, doctor: User):
        """Список пользователей."""
        from app.handlers.admin import cmd_list_users
        msg = make_message("/admin_list_users", user_id=111111)
        with patch("app.handlers.admin.Config") as mock_config:
            mock_config.ADMIN_IDS = [111111]
            await cmd_list_users(msg, db_session)
        msg.answer.assert_called()
        text = msg.answer.call_args[0][0]
        assert doctor.full_name in text

    @pytest.mark.asyncio
    async def test_errors_command(self):
        """Команда /errors возвращает статистику."""
        from app.handlers.admin import cmd_errors
        from app.services.error_monitor import ErrorMonitor

        monitor = ErrorMonitor()
        monitor._started_at = __import__("datetime").datetime.now()

        msg = make_message("/errors", user_id=111111)
        with patch("app.handlers.admin._is_admin", return_value=True), \
             patch("app.services.error_monitor.error_monitor", monitor):
            await cmd_errors(msg)
        msg.answer.assert_called_once()
        assert "Мониторинг" in msg.answer.call_args[0][0]
