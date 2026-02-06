from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.database.models import Appointment, User, ClinicLocation, Service
from sqlalchemy.orm import selectinload


async def get_appointments_by_date(
    db_session: AsyncSession,
    doctor_id: int,
    target_date: date
) -> List[Appointment]:
    """Получить записи на конкретную дату"""
    start_datetime = datetime.combine(target_date, datetime.min.time())
    end_datetime = datetime.combine(target_date, datetime.max.time())
    
    stmt = (
        select(Appointment)
        .options(
            selectinload(Appointment.patient),
            selectinload(Appointment.service),
            selectinload(Appointment.location),
        )
        .where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.date_time >= start_datetime,
                Appointment.date_time <= end_datetime,
                Appointment.status != "cancelled"
            )
        )
        .order_by(Appointment.date_time)
    )
    
    result = await db_session.execute(stmt)
    return list(result.scalars().all())


async def get_appointments_today(
    db_session: AsyncSession,
    doctor_id: int
) -> List[Appointment]:
    """Получить записи на сегодня"""
    today = date.today()
    return await get_appointments_by_date(db_session, doctor_id, today)


async def format_appointments_list(
    appointments: List[Appointment],
    show_price: bool = True
) -> str:
    """Форматирование списка записей для отображения"""
    if not appointments:
        return "📅 На этот день записей нет."
    
    lines = []
    for apt in appointments:
        time_str = apt.date_time.strftime("%H:%M")
        location_emoji = ""
        if apt.location:
            location_emoji = apt.location.emoji + " "
        
        patient_info = apt.patient.full_name if apt.patient else (apt.service_description or "Без описания")
        service_part = ""
        if apt.service:
            service_part = f" — {apt.service.name}"
            if show_price:
                from app.utils.formatters import format_money
                service_part += f" ({format_money(apt.service.price)})"
        elif apt.service_description and apt.patient:
            service_part = f" — {apt.service_description}"
        
        lines.append(f"{location_emoji}{time_str} - {patient_info}{service_part}")
    
    return "📅 **Расписание:**\n\n" + "\n".join(lines)


async def format_schedule_with_contacts(
    appointments: List[Appointment],
    show_price: bool = True
) -> str:
    """Форматирование расписания с ФИО, услугой и телефоном"""
    if not appointments:
        return "📅 На этот день записей нет."
    
    lines = []
    for apt in appointments:
        time_str = apt.date_time.strftime("%H:%M")
        patient_name = apt.patient.full_name if apt.patient else (apt.service_description or "Без описания")
        patient_phone = (apt.patient.phone or "—") if apt.patient else "—"
        
        service_line = ""
        if apt.service:
            service_line = f"🏥 Услуга: {apt.service.name}"
            if show_price:
                from app.utils.formatters import format_money
                service_line += f" — {format_money(apt.service.price)}"
            service_line += "\n"
        elif apt.service_description:
            service_line = f"🏥 Услуга: {apt.service_description}\n"
        
        lines.append(
            f"🕐 *{time_str}*\n"
            f"👤 {patient_name}\n"
            f"{service_line}"
            f"📞 {patient_phone}\n"
        )
    
    return "📋 **Расписание на день:**\n\n" + "\n".join(lines)


async def get_dates_with_appointments(
    db_session: AsyncSession,
    doctor_id: int,
    year: int,
    month: int
) -> List[date]:
    """Получить даты месяца, в которых есть записи"""
    start_datetime = datetime(year, month, 1)
    if month == 12:
        end_datetime = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_datetime = datetime(year, month + 1, 1) - timedelta(days=1)
    
    stmt = select(Appointment.date_time).where(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.date_time >= start_datetime,
            Appointment.date_time <= end_datetime,
            Appointment.status != "cancelled"
        )
    ).order_by(Appointment.date_time)
    
    result = await db_session.execute(stmt)
    appointments = result.scalars().all()
    # Уникальные даты
    dates_set = {apt.date() for apt in appointments}
    return sorted(dates_set)


async def get_busy_ranges_for_date(
    db_session: AsyncSession,
    doctor_id: int,
    target_date: date,
    exclude_appointment_id: int | None = None
) -> List[tuple]:
    """Занятые интервалы на дату: [(start, end), ...]. exclude_appointment_id — не учитывать при переносе"""
    appointments = await get_appointments_by_date(db_session, doctor_id, target_date)
    ranges = []
    for apt in appointments:
        if exclude_appointment_id and apt.id == exclude_appointment_id:
            continue
        start_dt = apt.date_time
        dur = getattr(apt, 'duration_minutes', None)
        if dur is None and apt.service:
            dur = getattr(apt.service, 'duration_minutes', 30)
        dur = dur or 30
        end_dt = start_dt + timedelta(minutes=dur)
        ranges.append((start_dt, end_dt))
    return ranges


def is_slot_available(
    slot_start: datetime,
    duration_minutes: int,
    busy_ranges: List[tuple]
) -> bool:
    """Проверка: слот [slot_start, slot_start+duration] не пересекается с занятыми"""
    slot_end = slot_start + timedelta(minutes=duration_minutes)
    for busy_start, busy_end in busy_ranges:
        if slot_start < busy_end and slot_end > busy_start:
            return False
    return True


async def get_clinic_locations(
    db_session: AsyncSession,
    doctor_id: int
) -> List[ClinicLocation]:
    """Получить список локаций врача"""
    stmt = select(ClinicLocation).where(
        ClinicLocation.doctor_id == doctor_id
    ).order_by(ClinicLocation.created_at)
    
    result = await db_session.execute(stmt)
    return list(result.scalars().all())

