from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Appointment, ClinicLocation, Treatment
from app.states.appointment import AppointmentStates
from app.keyboards.calendar import get_calendar_keyboard, get_time_slots_keyboard, get_schedule_dates_keyboard
from app.services.calendar_service import (
    get_appointments_by_date,
    get_appointments_today,
    format_appointments_list,
    format_schedule_with_contacts,
    get_dates_with_appointments,
    get_clinic_locations,
    get_busy_ranges_for_date,
)
from app.services.patient_service import search_patients
from app.services.service_service import (
    get_categories,
    get_services_by_category,
    ensure_default_services,
    get_service_by_id,
    CATEGORIES,
)
from app.utils.formatters import format_money, treatment_effective_price
from app.states.patient import PatientStates
from app.keyboards.main import get_cancel_keyboard, get_main_menu_keyboard
from app.utils.permissions import can_access, FEATURE_CALENDAR
from sqlalchemy import select, and_

router = Router(name="calendar")


@router.message(F.text == "📋 Расписание")
async def cmd_schedule_view(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Расписание — календарь дней с записями"""
    if not can_access(assistant_permissions, FEATURE_CALENDAR):
        await message.answer("Нет доступа к календарю.")
        return
    today = datetime.now()
    dates = await get_dates_with_appointments(db_session, effective_doctor.id, today.year, today.month)
    
    month_names = ["январе", "феврале", "марте", "апреле", "мае", "июне",
                   "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
    if not dates:
        await message.answer(
            f"📋 В {month_names[today.month-1]} {today.year} записей нет.\n\n"
            "Используйте стрелки для перехода к другому месяцу:",
            reply_markup=get_schedule_dates_keyboard([], today.year, today.month)
        )
    else:
        await message.answer(
            f"📋 Выберите день с записями ({month_names[today.month-1]} {today.year}):",
            reply_markup=get_schedule_dates_keyboard(dates, today.year, today.month)
        )


@router.message(Command("today"))
@router.message(F.text == "📅 Календарь")
async def cmd_calendar(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Показать календарь или расписание на сегодня"""
    if not can_access(assistant_permissions, FEATURE_CALENDAR):
        await message.answer("Нет доступа к календарю.")
        return
    if message.text == "📅 Календарь":
        today = datetime.now()
        await message.answer(
            "📅 Выберите дату:",
            reply_markup=get_calendar_keyboard(today.year, today.month)
        )
    else:
        appointments = await get_appointments_today(db_session, effective_doctor.id)
        show_price = effective_doctor.subscription_tier >= 1
        text = await format_appointments_list(appointments, show_price=show_price)
        await message.answer(text)


@router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Показать расписание на выбранную дату"""
    if not can_access(assistant_permissions, FEATURE_CALENDAR):
        await message.answer("Нет доступа к календарю.")
        return
    args = message.text.split()
    if len(args) > 1:
        try:
            target_date = datetime.strptime(args[1], "%Y-%m-%d").date()
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте: /schedule 2024-01-15")
            return
    else:
        target_date = date.today()
    appointments = await get_appointments_by_date(db_session, effective_doctor.id, target_date)
    show_price = effective_doctor.subscription_tier >= 1
    text = await format_appointments_list(appointments, show_price=show_price)
    await message.answer(text)


# Обработчики расписания
@router.callback_query(F.data.startswith("sched_"))
async def process_schedule_callback(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Обработка callback расписания"""
    data = callback.data
    
    if data == "sched_back":
        await callback.message.delete()
        tier_names = {0: "Basic", 1: "Standard", 2: "Premium"}
        tier_name = tier_names.get(effective_doctor.subscription_tier, "Basic")
        text = (
            f"📋 Главное меню\n\n"
            f"👤 {user.full_name}\n"
            f"🏥 {effective_doctor.specialization or 'Не указано'}\n"
            f"⭐ Уровень подписки: {tier_name}\n\n"
            f"Выберите действие:"
        )
        await callback.message.answer(text, reply_markup=get_main_menu_keyboard(user, effective_doctor, assistant_permissions))
        await callback.answer()
        return
    
    if data == "sched_none":
        await callback.answer()
        return
    
    if data.startswith("sched_prev_"):
        parts = data.replace("sched_prev_", "").split("_")
        year, month = int(parts[0]), int(parts[1])
        dates = await get_dates_with_appointments(db_session, effective_doctor.id, year, month)
        month_names = ["январе", "феврале", "марте", "апреле", "мае", "июне",
                       "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
        text = f"📋 Выберите день ({month_names[month-1]} {year}):"
        await callback.message.edit_text(text, reply_markup=get_schedule_dates_keyboard(dates, year, month))
        await callback.answer()
        return
    
    if data.startswith("sched_next_"):
        parts = data.replace("sched_next_", "").split("_")
        year, month = int(parts[0]), int(parts[1])
        dates = await get_dates_with_appointments(db_session, effective_doctor.id, year, month)
        month_names = ["январе", "феврале", "марте", "апреле", "мае", "июне",
                       "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
        text = f"📋 Выберите день ({month_names[month-1]} {year}):"
        await callback.message.edit_text(text, reply_markup=get_schedule_dates_keyboard(dates, year, month))
        await callback.answer()
        return
    
    if data.startswith("sched_date_"):
        parts = data.replace("sched_date_", "").split("_")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        target_date = date(year, month, day)
        
        appointments = await get_appointments_by_date(db_session, effective_doctor.id, target_date)
        show_price = effective_doctor.subscription_tier >= 1
        text = await format_schedule_with_contacts(appointments, show_price=show_price)
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for apt in appointments:
            builder.button(text="🗑 Удалить", callback_data=f"appt_cancel_{apt.id}")
            if effective_doctor.subscription_tier >= 1:
                builder.button(text="📅 Перенести", callback_data=f"appt_reschedule_{apt.id}")
        builder.button(text="← К календарю", callback_data=f"sched_month_{year}_{month}")
        builder.adjust(2 if effective_doctor.subscription_tier >= 1 else 1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        return
    
    if data.startswith("sched_month_"):
        parts = data.replace("sched_month_", "").split("_")
        year, month = int(parts[0]), int(parts[1])
        dates = await get_dates_with_appointments(db_session, effective_doctor.id, year, month)
        month_names = ["январе", "феврале", "марте", "апреле", "мае", "июне",
                       "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
        text = f"📋 Выберите день ({month_names[month-1]} {year}):"
        await callback.message.edit_text(text, reply_markup=get_schedule_dates_keyboard(dates, year, month))
        await callback.answer()
        return
    
    await callback.answer()


# Обработчики календаря
@router.callback_query(F.data.startswith("cal_"))
async def process_calendar_callback(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка callback от календаря"""
    data = callback.data
    
    if data == "cal_cancel":
        await callback.message.delete()
        await callback.answer()
        await state.clear()
        return
    
    if data == "cal_today":
        today = datetime.now()
        selected_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        await state.update_data(selected_date=selected_date)

        data_state = await state.get_data()
        if data_state.get("rescheduling_appointment_id"):
            appointment_id = data_state["rescheduling_appointment_id"]
            busy_ranges = await get_busy_ranges_for_date(
                db_session, effective_doctor.id, selected_date.date(), exclude_appointment_id=appointment_id
            )
            keyboard = get_time_slots_keyboard(
                selected_date=selected_date, busy_ranges=busy_ranges
            )
            await callback.message.edit_text(
                f"⏰ Выберите новое время для записи на {selected_date.strftime('%d.%m.%Y')}:",
                reply_markup=keyboard
            )
            await state.set_state(AppointmentStates.select_time)
            await callback.answer()
            return

        locations = await get_clinic_locations(db_session, effective_doctor.id)
        if len(locations) <= 1:
            if len(locations) == 1:
                await state.update_data(location_id=locations[0].id)
            if effective_doctor.subscription_tier >= 1:
                builder = InlineKeyboardBuilder()
                builder.button(text="🔍 Найти в базе", callback_data="appt_find_patient")
                builder.button(text="➕ Новый пациент", callback_data="appt_new_patient")
                builder.button(text="❌ Отмена", callback_data="appt_cancel")
                builder.adjust(2, 1)
                await callback.message.edit_text(
                    "👤 Выберите действие:",
                    reply_markup=builder.as_markup()
                )
                await state.set_state(AppointmentStates.select_or_create_patient)
            else:
                await callback.message.edit_text("⏰ Выберите время для записи на сегодня:")
                await callback.message.edit_reply_markup(reply_markup=get_time_slots_keyboard())
                await state.set_state(AppointmentStates.select_time)
        else:
            builder = InlineKeyboardBuilder()
            for loc in locations:
                builder.button(text=f"{loc.emoji} {loc.name}", callback_data=f"loc_{loc.id}")
            builder.button(text="❌ Отмена", callback_data="appt_cancel")
            builder.adjust(1)
            await callback.message.edit_text("🏥 Выберите локацию для записи на сегодня:")
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
            await state.set_state(AppointmentStates.select_location)

        await callback.answer()
        return

    if data.startswith("cal_date_"):
        # Выбрана дата
        parts = data.replace("cal_date_", "").split("_")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        selected_date = datetime(year, month, day)
        
        await state.update_data(selected_date=selected_date)
        
        # Проверяем, переносим ли мы запись
        data_state = await state.get_data()
        if data_state.get("rescheduling_appointment_id"):
            appointment_id = data_state["rescheduling_appointment_id"]
            busy_ranges = await get_busy_ranges_for_date(
                db_session, effective_doctor.id, selected_date.date(), exclude_appointment_id=appointment_id
            )
            keyboard = get_time_slots_keyboard(
                selected_date=selected_date, busy_ranges=busy_ranges
            )
            await callback.message.edit_text(
                f"⏰ Выберите новое время для записи на {selected_date.strftime('%d.%m.%Y')}:",
                reply_markup=keyboard
            )
            await state.set_state(AppointmentStates.select_time)
            await callback.answer()
            return
        
        locations = await get_clinic_locations(db_session, effective_doctor.id)
        
        if len(locations) <= 1:
            if len(locations) == 1:
                await state.update_data(location_id=locations[0].id)
            if effective_doctor.subscription_tier >= 1:
                builder = InlineKeyboardBuilder()
                builder.button(text="🔍 Найти в базе", callback_data="appt_find_patient")
                builder.button(text="➕ Новый пациент", callback_data="appt_new_patient")
                builder.button(text="❌ Отмена", callback_data="appt_cancel")
                builder.adjust(2, 1)
                await callback.message.edit_text(
                    "👤 Выберите действие:",
                    reply_markup=builder.as_markup()
                )
                await state.set_state(AppointmentStates.select_or_create_patient)
            else:
                await callback.message.edit_text("⏰ Выберите время:")
                await callback.message.edit_reply_markup(reply_markup=get_time_slots_keyboard())
                await state.set_state(AppointmentStates.select_time)
        else:
            # Если >1 локации, предлагаем выбрать
            builder = InlineKeyboardBuilder()
            for loc in locations:
                builder.button(text=f"{loc.emoji} {loc.name}", callback_data=f"loc_{loc.id}")
            builder.button(text="❌ Отмена", callback_data="appt_cancel")
            builder.adjust(1)
            
            await callback.message.edit_text("🏥 Выберите локацию:")
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
            await state.set_state(AppointmentStates.select_location)
        
        await callback.answer()
        return
    
    if data.startswith("cal_prev_"):
        parts = data.replace("cal_prev_", "").split("_")
        year, month = int(parts[0]), int(parts[1])
        prev_date = datetime(year, month, 1) - timedelta(days=1)
        await callback.message.edit_reply_markup(
            reply_markup=get_calendar_keyboard(prev_date.year, prev_date.month)
        )
        await callback.answer()
        return
    
    if data.startswith("cal_next_"):
        parts = data.replace("cal_next_", "").split("_")
        year, month = int(parts[0]), int(parts[1])
        if month == 12:
            next_date = datetime(year + 1, 1, 1)
        else:
            next_date = datetime(year, month + 1, 1)
        await callback.message.edit_reply_markup(
            reply_markup=get_calendar_keyboard(next_date.year, next_date.month)
        )
        await callback.answer()
        return
    
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_location), F.data.startswith("loc_"))
async def process_location_selection(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext
):
    """Обработка выбора локации"""
    if callback.data == "appt_cancel":
        await callback.message.delete()
        await callback.answer()
        await state.clear()
        return
    
    location_id = int(callback.data.replace("loc_", ""))
    await state.update_data(location_id=location_id)
    
    if effective_doctor.subscription_tier >= 1:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Найти в базе", callback_data="appt_find_patient")
        builder.button(text="➕ Новый пациент", callback_data="appt_new_patient")
        builder.button(text="❌ Отмена", callback_data="appt_cancel")
        builder.adjust(2, 1)
        await callback.message.edit_text(
            "👤 Выберите действие:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(AppointmentStates.select_or_create_patient)
    else:
        await callback.message.edit_text("⏰ Выберите время:")
        await callback.message.edit_reply_markup(reply_markup=get_time_slots_keyboard())
        await state.set_state(AppointmentStates.select_time)
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_time), F.data.startswith("time_"))
async def process_time_selection(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка выбора времени"""
    if callback.data == "time_cancel":
        await callback.message.delete()
        await callback.answer()
        await state.clear()
        return
    
    time_str = callback.data.replace("time_", "")
    data = await state.get_data()
    selected_date: datetime = data.get("selected_date")
    
    hour, minute = map(int, time_str.split(":"))
    appointment_datetime = selected_date.replace(hour=hour, minute=minute)
    
    rescheduling_id = data.get("rescheduling_appointment_id")
    if rescheduling_id:
        stmt = select(Appointment).where(
            and_(
                Appointment.id == rescheduling_id,
                Appointment.doctor_id == effective_doctor.id
            )
        )
        result = await db_session.execute(stmt)
        appointment = result.scalar_one_or_none()
        if appointment:
            appointment.date_time = appointment_datetime
            await db_session.commit()
            await callback.message.edit_text(
                f"✅ Запись перенесена!\n\n"
                f"📅 Новая дата и время: {appointment_datetime.strftime('%d.%m.%Y %H:%M')}"
            )
            await state.clear()
            await callback.answer()
            return
        await state.update_data(rescheduling_appointment_id=None)
    
    if data.get("service_name") or data.get("service_id"):
        service_id = data.get("service_id")
        service_name = data.get("service_name", "")
        service_price = data.get("service_price") or 0
        duration_minutes = data.get("service_duration_minutes", 30)
        patient_id = data.get("patient_id")
        location_id = data.get("location_id")

        if effective_doctor.subscription_tier >= 2 and service_price and float(service_price) > 0:
            await state.update_data(appointment_datetime=appointment_datetime)
            await callback.message.edit_text(
                f"📝 Услуга: **{service_name}** — {format_money(service_price)}\n\n"
                "💸 Скидка на эту услугу: введите **процент** (например 10 или 10%) или **сумму** (например 50 000), или /skip — без скидки:"
            )
            await state.set_state(AppointmentStates.enter_discount)
            await callback.answer()
            return

        appointment = Appointment(
            doctor_id=effective_doctor.id,
            patient_id=patient_id,
            service_id=service_id,
            location_id=location_id,
            date_time=appointment_datetime,
            duration_minutes=duration_minutes,
            service_description=service_name,
            status="planned"
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        treatment = Treatment(
            patient_id=patient_id,
            doctor_id=effective_doctor.id,
            appointment_id=appointment.id,
            service_name=service_name,
            price=service_price if effective_doctor.subscription_tier >= 2 else None,
        )
        db_session.add(treatment)
        await db_session.commit()

        await callback.message.edit_text(
            f"✅ Запись создана!\n\n"
            f"📅 Дата: {appointment_datetime.strftime('%d.%m.%Y %H:%M')}\n"
            f"📝 {service_name} — {format_money(service_price)}"
        )
        await state.clear()
        await callback.answer()
        return
    
    # Basic: текстовый ввод (время выбрано первым)
    await state.update_data(appointment_datetime=appointment_datetime)
    await callback.message.edit_text(
        "📝 Введите данные записи в формате:\n"
        "ФИО пациента - Название услуги\n\n"
        "Например: Иванов Иван Иванович - Консультация"
    )
    await state.set_state(AppointmentStates.enter_patient_name)
    await callback.answer()


@router.message(StateFilter(AppointmentStates.enter_discount), F.text)
async def process_appointment_discount(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Скидка на услугу при записи через расписание (Premium): процент, сумма или /skip"""
    text = (message.text or "").strip().lower()
    if text == "/skip" or not text:
        discount_percent = None
        discount_amount = None
    else:
        discount_percent = None
        discount_amount = None
        if "%" in message.text:
            try:
                num_str = message.text.replace("%", "").replace(",", ".").strip()
                discount_percent = float(num_str)
                if discount_percent < 0 or discount_percent > 100:
                    await message.answer("❌ Процент скидки от 0 до 100. Попробуйте снова:")
                    return
            except ValueError:
                await message.answer("❌ Введите процент (например 10 или 10%) или сумму, или /skip:")
                return
        else:
            try:
                num_str = message.text.replace(" ", "").replace(",", ".").strip()
                discount_amount = float(num_str)
                if discount_amount < 0:
                    await message.answer("❌ Сумма скидки не может быть отрицательной:")
                    return
            except ValueError:
                await message.answer("❌ Введите число (сумма скидки в сумах), процент (10%) или /skip:")
                return

    data = await state.get_data()
    appointment_datetime = data.get("appointment_datetime")
    service_id = data.get("service_id")
    service_name = data.get("service_name", "")
    service_price = float(data.get("service_price") or 0)
    duration_minutes = data.get("service_duration_minutes", 30)
    patient_id = data.get("patient_id")
    location_id = data.get("location_id")

    if not appointment_datetime or not patient_id:
        await message.answer("❌ Ошибка: не указаны дата или пациент. Начните запись заново.")
        await state.clear()
        return

    appointment = Appointment(
        doctor_id=effective_doctor.id,
        patient_id=patient_id,
        service_id=service_id,
        location_id=location_id,
        date_time=appointment_datetime,
        duration_minutes=duration_minutes,
        service_description=service_name,
        status="planned"
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)

    treatment = Treatment(
        patient_id=patient_id,
        doctor_id=effective_doctor.id,
        appointment_id=appointment.id,
        service_name=service_name,
        price=service_price,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
    )
    db_session.add(treatment)
    await db_session.commit()

    eff = treatment_effective_price(service_price, discount_percent, discount_amount)
    msg = (
        f"✅ Запись создана!\n\n"
        f"📅 Дата: {appointment_datetime.strftime('%d.%m.%Y %H:%M')}\n"
        f"📝 {service_name} — итого {format_money(eff)}"
    )
    if discount_percent or discount_amount:
        msg += " (со скидкой)"
    await message.answer(msg)
    await state.clear()


@router.message(StateFilter(AppointmentStates.enter_patient_name))
async def process_patient_name_basic(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка ввода данных для Basic"""
    service_description = message.text.strip()
    data = await state.get_data()
    appointment_datetime = data.get("appointment_datetime")
    location_id = data.get("location_id")
    
    appointment = Appointment(
        doctor_id=effective_doctor.id,
        patient_id=None,  # Для Basic
        location_id=location_id,
        date_time=appointment_datetime,
        duration_minutes=30,
        service_description=service_description,
        status="planned"
    )
    db_session.add(appointment)
    await db_session.commit()
    
    await message.answer(
        f"✅ Запись создана!\n\n"
        f"📅 Дата: {appointment_datetime.strftime('%d.%m.%Y %H:%M')}\n"
        f"📝 {service_description}"
    )
    await state.clear()


@router.callback_query(F.data == "appt_cancel")
async def cancel_appointment(callback: CallbackQuery, state: FSMContext):
    """Отмена записи"""
    await callback.message.delete()
    await callback.answer("❌ Запись отменена")
    await state.clear()


# Обработчики для Standard+ (выбор/создание пациента)
@router.callback_query(StateFilter(AppointmentStates.select_or_create_patient), F.data == "appt_find_patient")
async def find_patient_for_appointment(callback: CallbackQuery, user: User, state: FSMContext, db_session: AsyncSession):
    """Поиск пациента для записи"""
    await callback.message.edit_text(
        "🔍 Введите ФИО или телефон пациента для поиска:"
    )
    await state.set_state(AppointmentStates.select_or_create_patient)
    await state.update_data(search_mode=True)
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_or_create_patient), F.data == "appt_new_patient")
async def new_patient_for_appointment(callback: CallbackQuery, state: FSMContext):
    """Создание нового пациента для записи"""
    await callback.message.edit_text(
        "➕ Создание нового пациента\n\n"
        "Введите ФИО пациента:"
    )
    await state.set_state(PatientStates.enter_full_name)
    await state.update_data(creating_for_appointment=True)
    await callback.answer()


@router.message(StateFilter(AppointmentStates.select_or_create_patient))
async def process_patient_search_for_appointment(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка поиска пациента для записи — всегда показываем выбор по результатам"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    data = await state.get_data()
    if not data.get("search_mode"):
        return
    
    query = message.text.strip()
    if not query:
        await message.answer("❌ Введите ФИО или телефон для поиска:")
        return
    
    patients = await search_patients(db_session, effective_doctor.id, query)
    
    if not patients:
        await message.answer(
            f"❌ По запросу «{query}» пациенты не найдены.\n\n"
            "Попробуйте другой поиск или создайте нового пациента."
        )
        return
    
    # Всегда показываем выбор по результатам поиска
    builder = InlineKeyboardBuilder()
    for patient in patients[:15]:
        # ФИО + телефон для удобного выбора
        phone_str = f" — {patient.phone}" if patient.phone else ""
        button_text = f"{patient.full_name}{phone_str}"
        if len(button_text) > 60:  # Ограничение Telegram
            button_text = patient.full_name[:57] + "..."
        builder.button(
            text=button_text,
            callback_data=f"appt_select_patient_{patient.id}"
        )
    builder.button(text="➕ Создать нового пациента", callback_data="appt_new_patient")
    builder.adjust(1)
    
    await message.answer(
        f"🔍 По запросу «{query}» найдено: {len(patients)}\n\n"
        "Выберите пациента из списка:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("appt_select_patient_"))
async def select_patient_for_appointment(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Выбор пациента для записи"""
    patient_id = int(callback.data.replace("appt_select_patient_", ""))
    await state.update_data(patient_id=patient_id)
    await callback.message.delete()
    await _continue_appointment_creation(callback.message, effective_doctor, state, db_session)
    await callback.answer()


async def _continue_appointment_creation(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Продолжение создания записи — выбор услуги по категориям"""
    await ensure_default_services(db_session, effective_doctor.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"appt_cat_{cat_id}")
    builder.button(text="📝 Другое (ввести вручную)", callback_data="appt_service_other")
    builder.adjust(2)

    await message.answer(
        "📋 Выберите категорию услуги:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AppointmentStates.select_service_category)


@router.callback_query(StateFilter(AppointmentStates.select_service_category), F.data.startswith("appt_cat_"))
async def process_service_category(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Выбор категории — показываем услуги"""
    category = callback.data.replace("appt_cat_", "")
    await state.update_data(service_category=category)

    services = await get_services_by_category(db_session, effective_doctor.id, category)
    cat_name, cat_emoji = CATEGORIES.get(category, ("", ""))

    builder = InlineKeyboardBuilder()
    for svc in services:
        text = f"{svc.name} — {format_money(svc.price)}"
        if len(text) > 60:
            text = svc.name[:50] + "..."
        builder.button(text=text, callback_data=f"appt_svc_{svc.id}")
    builder.button(text="← Назад к категориям", callback_data="appt_cat_back")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📋 {cat_emoji} {cat_name}\n\nВыберите услугу:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AppointmentStates.select_service)
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_service_category), F.data == "appt_service_other")
async def process_service_other(
    callback: CallbackQuery,
    user: User,
    state: FSMContext
):
    """Ввод услуги вручную"""
    await callback.message.edit_text("📝 Введите описание услуги:")
    await state.set_state(AppointmentStates.enter_service)
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_service), F.data == "appt_cat_back")
async def process_service_back(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Назад к категориям"""
    await ensure_default_services(db_session, effective_doctor.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"appt_cat_{cat_id}")
    builder.button(text="📝 Другое (ввести вручную)", callback_data="appt_service_other")
    builder.adjust(2)

    await callback.message.edit_text(
        "📋 Выберите категорию услуги:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AppointmentStates.select_service_category)
    await callback.answer()


@router.callback_query(StateFilter(AppointmentStates.select_service), F.data.startswith("appt_svc_"))
async def process_service_selection(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Выбор услуги — переходим к выбору времени (слоты блокируются по длительности)"""
    service_id = int(callback.data.replace("appt_svc_", ""))
    service = await get_service_by_id(db_session, service_id, effective_doctor.id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    data = await state.get_data()
    selected_date: datetime = data.get("selected_date")
    location_id = data.get("location_id")
    patient_id = data.get("patient_id")

    duration_minutes = getattr(service, 'duration_minutes', 30)
    await state.update_data(
        service_id=service.id,
        service_name=service.name,
        service_price=service.price,
        service_duration_minutes=duration_minutes,
        patient_id=patient_id,
    )

    busy_ranges = await get_busy_ranges_for_date(db_session, effective_doctor.id, selected_date.date())
    keyboard = get_time_slots_keyboard(
        selected_date=selected_date,
        duration_minutes=duration_minutes,
        busy_ranges=busy_ranges,
    )

    await callback.message.edit_text(
        f"⏰ Выберите время для {service.name} ({duration_minutes} мин):"
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await state.set_state(AppointmentStates.select_time)
    await callback.answer()


@router.message(StateFilter(AppointmentStates.enter_service))
async def process_service_description(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка текстового ввода услуги (Другое) — переход к выбору времени"""
    service_description = message.text.strip()
    if not service_description:
        await message.answer("❌ Введите описание услуги:")
        return

    data = await state.get_data()
    selected_date: datetime = data.get("selected_date")
    location_id = data.get("location_id")
    patient_id = data.get("patient_id")

    await state.update_data(
        service_id=None,
        service_name=service_description,
        service_price=0,
        service_duration_minutes=30,
        patient_id=patient_id,
    )

    busy_ranges = await get_busy_ranges_for_date(db_session, effective_doctor.id, selected_date.date())
    keyboard = get_time_slots_keyboard(
        selected_date=selected_date,
        duration_minutes=30,
        busy_ranges=busy_ranges,
    )

    await message.answer(
        f"⏰ Выберите время для «{service_description}» (30 мин):",
        reply_markup=keyboard
    )
    await state.set_state(AppointmentStates.select_time)


# Управление визитами (отмена, перенос)
@router.callback_query(F.data.startswith("appt_cancel_"))
async def cancel_existing_appointment(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession
):
    """Удаление (отмена) записи — возврат к расписанию на день"""
    appointment_id = int(callback.data.replace("appt_cancel_", ""))
    
    from sqlalchemy import select
    stmt = select(Appointment).where(
        and_(
            Appointment.id == appointment_id,
            Appointment.doctor_id == effective_doctor.id
        )
    )
    result = await db_session.execute(stmt)
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    target_date = appointment.date_time.date()
    appointment.status = "cancelled"
    await db_session.commit()
    
    appointments = await get_appointments_by_date(db_session, effective_doctor.id, target_date)
    show_price = effective_doctor.subscription_tier >= 1
    text = await format_schedule_with_contacts(appointments, show_price=show_price)
    if not appointments:
        text = f"📋 **Расписание на {target_date.strftime('%d.%m.%Y')}**\n\n✅ Запись отменена. На этот день записей не осталось."
    else:
        text = "✅ Запись удалена.\n\n" + text
    
    builder = InlineKeyboardBuilder()
    for apt in appointments:
        builder.button(text="🗑 Удалить", callback_data=f"appt_cancel_{apt.id}")
        if effective_doctor.subscription_tier >= 1:
            builder.button(text="📅 Перенести", callback_data=f"appt_reschedule_{apt.id}")
    y, m, d = target_date.year, target_date.month, target_date.day
    builder.button(text="← К календарю", callback_data=f"sched_month_{y}_{m}")
    builder.adjust(2 if effective_doctor.subscription_tier >= 1 else 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("✅ Запись удалена")


@router.callback_query(F.data.startswith("appt_reschedule_"))
async def reschedule_appointment(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Перенос записи"""
    appointment_id = int(callback.data.replace("appt_reschedule_", ""))
    
    from sqlalchemy import select
    stmt = select(Appointment).where(
        and_(
            Appointment.id == appointment_id,
            Appointment.doctor_id == effective_doctor.id
        )
    )
    result = await db_session.execute(stmt)
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    await state.update_data(rescheduling_appointment_id=appointment_id)
    
    # Показываем календарь для выбора новой даты
    today = datetime.now()
    await callback.message.edit_text(
        "📅 Выберите новую дату для записи:",
        reply_markup=get_calendar_keyboard(today.year, today.month)
    )
    await state.set_state(AppointmentStates.select_date)
    await callback.answer()

