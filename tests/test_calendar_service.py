"""Интеграционные тесты calendar_service с in-memory SQLite."""
from datetime import datetime, date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Patient, Appointment
from app.services.calendar_service import (
    get_appointments_by_date,
    get_dates_with_appointments,
    format_appointments_list,
    is_slot_available,
)


@pytest.mark.asyncio
async def test_get_appointments_by_date(db_session: AsyncSession, doctor: User, appointment: Appointment):
    """Записи на конкретную дату возвращаются."""
    result = await get_appointments_by_date(db_session, doctor.id, date(2026, 3, 17))
    assert len(result) == 1
    assert result[0].id == appointment.id


@pytest.mark.asyncio
async def test_get_appointments_by_date_empty(db_session: AsyncSession, doctor: User):
    """Нет записей — пустой список."""
    result = await get_appointments_by_date(db_session, doctor.id, date(2026, 1, 1))
    assert result == []


@pytest.mark.asyncio
async def test_cancelled_excluded(db_session: AsyncSession, doctor: User, appointment: Appointment):
    """Отменённые записи не возвращаются."""
    appointment.status = "cancelled"
    await db_session.commit()
    result = await get_appointments_by_date(db_session, doctor.id, date(2026, 3, 17))
    assert len(result) == 0


@pytest.mark.asyncio
async def test_other_doctor_not_visible(db_session: AsyncSession, doctor: User, appointment: Appointment):
    """Записи другого врача не видны."""
    other = User(telegram_id=222222, full_name="Другой Врач", subscription_tier=0, role="owner", registration_completed=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    result = await get_appointments_by_date(db_session, other.id, date(2026, 3, 17))
    assert result == []


@pytest.mark.asyncio
async def test_get_dates_with_appointments(db_session: AsyncSession, doctor: User, patient: Patient):
    """Возвращаются уникальные даты с записями."""
    for day in [5, 5, 10, 20]:
        apt = Appointment(
            doctor_id=doctor.id, patient_id=patient.id,
            date_time=datetime(2026, 3, day, 10, 0),
            duration_minutes=30, status="planned",
        )
        db_session.add(apt)
    await db_session.commit()

    dates = await get_dates_with_appointments(db_session, doctor.id, 2026, 3)
    assert date(2026, 3, 5) in dates
    assert date(2026, 3, 10) in dates
    assert date(2026, 3, 20) in dates
    # 5-е число было дважды, но должно быть одно
    assert len([d for d in dates if d == date(2026, 3, 5)]) == 1


@pytest.mark.asyncio
async def test_format_appointments_list_empty():
    result = await format_appointments_list([])
    assert "записей нет" in result


class TestIsSlotAvailable:

    def test_free_slot(self):
        busy = [(datetime(2026, 3, 17, 10, 0), datetime(2026, 3, 17, 10, 30))]
        assert is_slot_available(datetime(2026, 3, 17, 11, 0), 30, busy) is True

    def test_overlapping_slot(self):
        busy = [(datetime(2026, 3, 17, 10, 0), datetime(2026, 3, 17, 10, 30))]
        assert is_slot_available(datetime(2026, 3, 17, 10, 15), 30, busy) is False

    def test_adjacent_slot(self):
        """Слот сразу после занятого — доступен."""
        busy = [(datetime(2026, 3, 17, 10, 0), datetime(2026, 3, 17, 10, 30))]
        assert is_slot_available(datetime(2026, 3, 17, 10, 30), 30, busy) is True

    def test_no_busy_ranges(self):
        assert is_slot_available(datetime(2026, 3, 17, 10, 0), 60, []) is True

    def test_multiple_busy_ranges(self):
        busy = [
            (datetime(2026, 3, 17, 9, 0), datetime(2026, 3, 17, 9, 30)),
            (datetime(2026, 3, 17, 10, 0), datetime(2026, 3, 17, 11, 0)),
        ]
        # Между 9:30 и 10:00 — 30 мин, слот помещается
        assert is_slot_available(datetime(2026, 3, 17, 9, 30), 30, busy) is True
        # 60 мин не помещается
        assert is_slot_available(datetime(2026, 3, 17, 9, 30), 60, busy) is False
