"""Сервис напоминаний о записях"""
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database.models import Appointment, User, Patient

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
    Возвращает список (appointment, doctor_user, reminder_minutes).
    """
    now = datetime.now()
    # Будущие записи на ближайшие 25 часов (чтобы поймать напоминания за 24ч)
    end_window = now + timedelta(hours=25)

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
                Appointment.date_time > now,
                Appointment.date_time <= end_window,
            )
        )
    )
    result = await db_session.execute(stmt)
    rows = result.all()

    due = []
    for apt, doctor in rows:
        reminder_mins = get_reminder_minutes(doctor)
        reminder_at = apt.date_time - timedelta(minutes=reminder_mins)
        # Отправить, если текущее время >= времени напоминания (с допуском 1 мин)
        if now >= reminder_at - timedelta(seconds=30):
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
