"""Тесты хендлеров календаря и расписания с реальной БД (SQLite)."""
import pytest
import pytest_asyncio
from datetime import datetime, date

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Patient, Appointment
from app.handlers.calendar import cmd_schedule_view, process_schedule_callback
from app.services.calendar_service import (
    get_appointments_by_date,
    get_dates_with_appointments,
    format_appointments_list,
    format_schedule_with_contacts,
    get_busy_ranges_for_date,
)
from app.utils.permissions import full_permissions, LEVEL_NONE, FEATURE_CALENDAR
from tests.helpers import make_message, make_callback, make_state


class TestCalendarService:
    """Тесты сервисного слоя календаря."""

    @pytest.mark.asyncio
    async def test_get_appointments_empty(self, db_session: AsyncSession, doctor: User):
        """Нет записей на дату — пустой список."""
        result = await get_appointments_by_date(db_session, doctor.id, date(2026, 1, 1))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_appointments_by_date(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Запись найдена по дате."""
        result = await get_appointments_by_date(db_session, doctor.id, date(2026, 3, 17))
        assert len(result) == 1
        assert result[0].id == appointment.id

    @pytest.mark.asyncio
    async def test_cancelled_not_shown(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Отменённые записи не показываются."""
        appointment.status = "cancelled"
        await db_session.commit()
        result = await get_appointments_by_date(db_session, doctor.id, date(2026, 3, 17))
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_other_doctor_not_visible(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Записи другого врача не видны."""
        other = User(telegram_id=222222, full_name="Другой", role="owner", registration_completed=True)
        db_session.add(other)
        await db_session.commit()
        result = await get_appointments_by_date(db_session, other.id, date(2026, 3, 17))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_dates_with_appointments(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Дни с записями возвращаются."""
        dates = await get_dates_with_appointments(db_session, doctor.id, 2026, 3)
        assert date(2026, 3, 17) in dates

    @pytest.mark.asyncio
    async def test_get_dates_empty_month(self, db_session: AsyncSession, doctor: User):
        """Пустой месяц — нет дат."""
        dates = await get_dates_with_appointments(db_session, doctor.id, 2025, 1)
        assert dates == []

    @pytest.mark.asyncio
    async def test_busy_ranges(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Занятые интервалы корректно определяются."""
        ranges = await get_busy_ranges_for_date(db_session, doctor.id, date(2026, 3, 17))
        assert len(ranges) >= 1

    @pytest.mark.asyncio
    async def test_busy_ranges_exclude_appointment(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Исключение записи из busy ranges (при переносе)."""
        ranges = await get_busy_ranges_for_date(
            db_session, doctor.id, date(2026, 3, 17), exclude_appointment_id=appointment.id
        )
        assert len(ranges) == 0


class TestFormatting:
    """Тесты форматирования расписания."""

    @pytest.mark.asyncio
    async def test_format_empty(self):
        text = await format_appointments_list([])
        assert "записей нет" in text.lower()

    @pytest.mark.asyncio
    async def test_format_with_appointment(self, appointment: Appointment):
        text = await format_appointments_list([appointment])
        assert "14:00" in text
        assert "Консультация" in text

    @pytest.mark.asyncio
    async def test_format_schedule_with_contacts(self, appointment: Appointment):
        text = await format_schedule_with_contacts([appointment])
        assert "14:00" in text


class TestScheduleHandler:
    """Тесты хендлера расписания (cmd_schedule_view)."""

    @pytest.mark.asyncio
    async def test_schedule_no_access(self, db_session: AsyncSession, doctor: User):
        """Нет доступа к календарю → сообщение об ошибке."""
        msg = make_message("📋 Расписание", user_id=doctor.telegram_id)
        perms = {FEATURE_CALENDAR: LEVEL_NONE}
        await cmd_schedule_view(msg, doctor, doctor, perms, db_session)
        msg.answer.assert_called_once()
        assert "доступ" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_schedule_empty_month(self, db_session: AsyncSession, doctor: User):
        """Пустой месяц — показывает сообщение «нет записей»."""
        msg = make_message("📋 Расписание", user_id=doctor.telegram_id)
        await cmd_schedule_view(msg, doctor, doctor, full_permissions(), db_session)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "записей нет" in text.lower() or "выберите" in text.lower()

    @pytest.mark.asyncio
    async def test_schedule_with_appointments(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """Есть записи — показывает календарь с кнопками."""
        msg = make_message("📋 Расписание", user_id=doctor.telegram_id)
        await cmd_schedule_view(msg, doctor, doctor, full_permissions(), db_session)
        msg.answer.assert_called_once()
        # Должна быть inline-клавиатура
        assert msg.answer.call_args[1].get("reply_markup") is not None


class TestScheduleCallbacks:
    """Тесты callback-обработчиков расписания."""

    @pytest.mark.asyncio
    async def test_sched_none_noop(self, db_session: AsyncSession, doctor: User):
        """sched_none — просто answer() без изменений."""
        cb = make_callback("sched_none", user_id=doctor.telegram_id)
        await process_schedule_callback(cb, doctor, doctor, full_permissions(), db_session)
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_sched_date_shows_appointments(self, db_session: AsyncSession, doctor: User, appointment: Appointment):
        """sched_date_ — показывает записи на день."""
        cb = make_callback("sched_date_2026_3_17", user_id=doctor.telegram_id)
        await process_schedule_callback(cb, doctor, doctor, full_permissions(), db_session)
        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "14:00" in text

    @pytest.mark.asyncio
    async def test_sched_prev_navigates(self, db_session: AsyncSession, doctor: User):
        """sched_prev_ — переход к предыдущему месяцу."""
        cb = make_callback("sched_prev_2026_2", user_id=doctor.telegram_id)
        await process_schedule_callback(cb, doctor, doctor, full_permissions(), db_session)
        cb.message.edit_text.assert_called_once()
        assert "Февраль" in cb.message.edit_text.call_args[0][0] or "феврал" in cb.message.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_sched_next_navigates(self, db_session: AsyncSession, doctor: User):
        """sched_next_ — переход к следующему месяцу."""
        cb = make_callback("sched_next_2026_4", user_id=doctor.telegram_id)
        await process_schedule_callback(cb, doctor, doctor, full_permissions(), db_session)
        cb.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_sched_month_returns_to_calendar(self, db_session: AsyncSession, doctor: User):
        """sched_month_ — возврат к календарю месяца."""
        cb = make_callback("sched_month_2026_3", user_id=doctor.telegram_id)
        await process_schedule_callback(cb, doctor, doctor, full_permissions(), db_session)
        cb.message.edit_text.assert_called_once()
