"""Уведомления о новых записях врачу и ассистентам."""
import logging
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Appointment, User, DoctorAssistant, Patient

logger = logging.getLogger(__name__)


async def notify_new_appointment(
    bot: Bot,
    db_session: AsyncSession,
    appointment: Appointment,
    created_by_telegram_id: int,
):
    """
    Уведомить врача и его ассистентов о новой записи.
    Не отправляет уведомление тому, кто создал запись (created_by_telegram_id).
    """
    # Загружаем врача
    doctor_stmt = select(User).where(User.id == appointment.doctor_id)
    doctor = (await db_session.execute(doctor_stmt)).scalar_one_or_none()
    if not doctor:
        return

    # Загружаем пациента
    patient_name = "—"
    if appointment.patient_id:
        patient_stmt = select(Patient).where(Patient.id == appointment.patient_id)
        patient = (await db_session.execute(patient_stmt)).scalar_one_or_none()
        if patient:
            patient_name = patient.full_name

    # Форматируем сообщение
    date_str = appointment.date_time.strftime("%d.%m.%Y")
    time_str = appointment.date_time.strftime("%H:%M")
    service = appointment.service_description or "Не указана"
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[appointment.date_time.weekday()]

    text = (
        "📌 **Новая запись!**\n\n"
        f"👤 {patient_name}\n"
        f"📅 {date_str} ({day_name}) в {time_str}\n"
        f"🏥 {service}"
    )

    # Собираем получателей: врач + ассистенты (кроме создателя)
    recipients = set()

    if doctor.telegram_id != created_by_telegram_id:
        recipients.add(doctor.telegram_id)

    # Ассистенты врача
    assistants_stmt = (
        select(User.telegram_id)
        .join(DoctorAssistant, DoctorAssistant.assistant_id == User.id)
        .where(DoctorAssistant.doctor_id == doctor.id)
    )
    result = await db_session.execute(assistants_stmt)
    for (tid,) in result.all():
        if tid != created_by_telegram_id:
            recipients.add(tid)

    # Отправляем
    for tid in recipients:
        try:
            await bot.send_message(tid, text)
        except Exception as e:
            logger.warning("Не удалось отправить уведомление %s: %s", tid, e)
