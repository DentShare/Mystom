"""Уведомления врачу и ассистентам: записи, изменения, редактирование пациентов."""
import logging
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Appointment, User, DoctorAssistant, Patient

logger = logging.getLogger(__name__)


async def _get_team_recipients(
    db_session: AsyncSession,
    doctor_id: int,
    exclude_telegram_id: int,
) -> set[int]:
    """Собрать telegram_id врача + всех ассистентов, исключая того кто сделал действие."""
    # Врач
    doctor_stmt = select(User).where(User.id == doctor_id)
    doctor = (await db_session.execute(doctor_stmt)).scalar_one_or_none()
    if not doctor:
        return set()

    recipients = set()
    if doctor.telegram_id != exclude_telegram_id:
        recipients.add(doctor.telegram_id)

    # Ассистенты
    assistants_stmt = (
        select(User.telegram_id)
        .join(DoctorAssistant, DoctorAssistant.assistant_id == User.id)
        .where(DoctorAssistant.doctor_id == doctor_id)
    )
    result = await db_session.execute(assistants_stmt)
    for (tid,) in result.all():
        if tid != exclude_telegram_id:
            recipients.add(tid)

    return recipients


async def _get_actor_name(db_session: AsyncSession, telegram_id: int) -> str:
    """Имя пользователя по telegram_id (для 'Кто сделал')."""
    stmt = select(User.full_name).where(User.telegram_id == telegram_id)
    result = (await db_session.execute(stmt)).scalar_one_or_none()
    return result or "Неизвестный"


async def _send_to_recipients(bot: Bot, recipients: set[int], text: str) -> None:
    """Отправка сообщения всем получателям."""
    for tid in recipients:
        try:
            await bot.send_message(tid, text)
        except Exception as e:
            logger.warning("Не удалось отправить уведомление %s: %s", tid, e)


def _format_appointment_info(appointment: Appointment, patient_name: str = "—") -> str:
    """Форматирование инфо о записи."""
    date_str = appointment.date_time.strftime("%d.%m.%Y")
    time_str = appointment.date_time.strftime("%H:%M")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[appointment.date_time.weekday()]
    service = appointment.service_description or "Не указана"
    return (
        f"👤 {patient_name}\n"
        f"📅 {date_str} ({day_name}) в {time_str}\n"
        f"🏥 {service}"
    )


async def _get_patient_name(db_session: AsyncSession, patient_id: int | None) -> str:
    if not patient_id:
        return "—"
    stmt = select(Patient.full_name).where(Patient.id == patient_id)
    return (await db_session.execute(stmt)).scalar_one_or_none() or "—"


# ── Уведомления о записях ─────────────────────────────────────────────

async def notify_new_appointment(
    bot: Bot,
    db_session: AsyncSession,
    appointment: Appointment,
    created_by_telegram_id: int,
):
    """Новая запись создана."""
    patient_name = await _get_patient_name(db_session, appointment.patient_id)
    actor = await _get_actor_name(db_session, created_by_telegram_id)
    info = _format_appointment_info(appointment, patient_name)

    text = f"📌 **Новая запись!**\n👷 {actor}\n\n{info}"

    recipients = await _get_team_recipients(db_session, appointment.doctor_id, created_by_telegram_id)
    await _send_to_recipients(bot, recipients, text)


async def notify_appointment_cancelled(
    bot: Bot,
    db_session: AsyncSession,
    appointment: Appointment,
    cancelled_by_telegram_id: int,
):
    """Запись отменена/удалена."""
    patient_name = await _get_patient_name(db_session, appointment.patient_id)
    actor = await _get_actor_name(db_session, cancelled_by_telegram_id)
    info = _format_appointment_info(appointment, patient_name)

    text = f"🗑 **Запись удалена**\n👷 {actor}\n\n{info}"

    recipients = await _get_team_recipients(db_session, appointment.doctor_id, cancelled_by_telegram_id)
    await _send_to_recipients(bot, recipients, text)


async def notify_appointment_rescheduled(
    bot: Bot,
    db_session: AsyncSession,
    appointment: Appointment,
    old_datetime_str: str,
    rescheduled_by_telegram_id: int,
):
    """Запись перенесена."""
    patient_name = await _get_patient_name(db_session, appointment.patient_id)
    actor = await _get_actor_name(db_session, rescheduled_by_telegram_id)
    new_str = appointment.date_time.strftime("%d.%m.%Y %H:%M")
    service = appointment.service_description or "Не указана"

    text = (
        f"📅 **Запись перенесена**\n"
        f"👷 {actor}\n\n"
        f"👤 {patient_name}\n"
        f"🏥 {service}\n"
        f"🕐 Было: {old_datetime_str}\n"
        f"🕑 Стало: {new_str}"
    )

    recipients = await _get_team_recipients(db_session, appointment.doctor_id, rescheduled_by_telegram_id)
    await _send_to_recipients(bot, recipients, text)


# ── Уведомления о пациентах ───────────────────────────────────────────

async def notify_patient_changed(
    bot: Bot,
    db_session: AsyncSession,
    doctor_id: int,
    patient_name: str,
    field_label: str,
    old_value: str,
    new_value: str,
    changed_by_telegram_id: int,
):
    """Данные пациента изменены."""
    actor = await _get_actor_name(db_session, changed_by_telegram_id)

    text = (
        f"✏️ **Пациент изменён**\n"
        f"👷 {actor}\n\n"
        f"👤 {patient_name}\n"
        f"📝 {field_label}: {old_value} → {new_value}"
    )

    recipients = await _get_team_recipients(db_session, doctor_id, changed_by_telegram_id)
    await _send_to_recipients(bot, recipients, text)


async def notify_patient_created(
    bot: Bot,
    db_session: AsyncSession,
    doctor_id: int,
    patient: Patient,
    created_by_telegram_id: int,
):
    """Новый пациент добавлен."""
    actor = await _get_actor_name(db_session, created_by_telegram_id)
    phone = patient.phone or "не указан"

    text = (
        f"➕ **Новый пациент**\n"
        f"👷 {actor}\n\n"
        f"👤 {patient.full_name}\n"
        f"📞 {phone}"
    )

    recipients = await _get_team_recipients(db_session, doctor_id, created_by_telegram_id)
    await _send_to_recipients(bot, recipients, text)
