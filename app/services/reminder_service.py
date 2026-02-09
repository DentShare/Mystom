"""Сервис напоминаний о записях. Время записей в БД — локальное (врача); сервер в UTC."""
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database.models import Appointment, User, Patient
from app.services.timezone import local_to_utc

logger = logging.getLogger(__name__)

DEFAULT_REMINDER_MINUTES = 30


def get_reminder_minutes(user: User) -> int:
    """Время напоминания в минутах (Standard/Premium могут менять, Basic — 30)"""
    if not user.settings or not isinstance(user.settings, dict):
        return DEFAULT_REMINDER_MINUTES
    val = user.settings.get("reminder_minutes")
    if val is None:
        return DEFAULT_REMINDER_MINUTES
    try:
        return max(5, min(1440, int(val)))  # 5 мин — 24 часа
    except (TypeError, ValueError):
        return DEFAULT_REMINDER_MINUTES


async def get_appointments_due_for_reminder(
    db_session: AsyncSession
) -> List[tuple[Appointment, User, int]]:
    """
    Найти записи, по которым пора отправить напоминание.
    date_time в БД хранится как локальное время врача; сравнение с now в UTC.
    """
    now_utc = datetime.utcnow()
    # Широкое окно: в БД — локальное время врача, точная проверка в цикле по UTC
    start_window = now_utc - timedelta(hours=1)
    end_window = now_utc + timedelta(hours=50)

    stmt = (
        select(Appointment, User)
        .join(User, Appointment.doctor_id == User.id)
        .options(
            selectinload(Appointment.patient),
            selectinload(Appointment.service),
        )
        .where(
            and_(
                Appointment.status == "planned",
                Appointment.reminder_sent_at.is_(None),
                Appointment.date_time > start_window,
                Appointment.date_time <= end_window,
            )
        )
    )
    result = await db_session.execute(stmt)
    rows = result.all()

    due = []
    for apt, doctor in rows:
        # Время записи в БД — локальное у врача; переводим в UTC для сравнения
        apt_utc = local_to_utc(apt.date_time, doctor.timezone)
        if apt_utc <= now_utc:
            continue  # запись уже в прошлом по UTC
        reminder_mins = get_reminder_minutes(doctor)
        reminder_at_utc = apt_utc - timedelta(minutes=reminder_mins)
        if now_utc >= reminder_at_utc - timedelta(seconds=30):
            due.append((apt, doctor, reminder_mins))

    return due


def format_reminder_message(apt: Appointment, reminder_mins: int) -> str:
    """Форматирование текста напоминания"""
    time_str = apt.date_time.strftime("%H:%M")
    date_str = apt.date_time.strftime("%d.%m.%Y")
    patient_name = "Пациент"
    if apt.patient:
        patient_name = apt.patient.full_name or "Пациент"
    service = apt.service_description or (apt.service.name if apt.service else "Приём")
    return (
        f"⏰ **Напоминание**\n\n"
        f"Через {reminder_mins} мин приём:\n"
        f"📅 {date_str} в {time_str}\n"
        f"👤 {patient_name}\n"
        f"📝 {service}"
    )
