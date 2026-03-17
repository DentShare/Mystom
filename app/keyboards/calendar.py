import calendar as cal_stdlib
from datetime import datetime, timedelta, date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.calendar_service import is_slot_available

# Названия для локализации
RU_MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
RU_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def get_calendar_keyboard(year: int, month: int, selected_date: datetime | None = None) -> InlineKeyboardMarkup:
    """Inline-календарь для выбора даты"""
    markup = []

    # 1. Навигация и месяц
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    row_header = [
        InlineKeyboardButton(text="◀️", callback_data=f"cal_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text=f"{RU_MONTHS[month]} {year}", callback_data="cal_none"),
        InlineKeyboardButton(text="▶️", callback_data=f"cal_next_{next_year}_{next_month}"),
    ]
    markup.append(row_header)

    # 2. Дни недели
    row_weekdays = [
        InlineKeyboardButton(text=day, callback_data="cal_none")
        for day in RU_WEEKDAYS
    ]
    markup.append(row_weekdays)

    # 3. Дни месяца (через monthcalendar)
    month_cal = cal_stdlib.monthcalendar(year, month)
    today = datetime.now().date()

    for week in month_cal:
        row_days = []
        for day in week:
            if day == 0:
                row_days.append(InlineKeyboardButton(text=" ", callback_data="cal_none"))
            else:
                date_obj = date(year, month, day)
                is_today = date_obj == today
                is_selected = selected_date and date_obj == selected_date.date() if selected_date else False
                text = str(day)
                if is_today:
                    text = f"•{day}•"
                if is_selected:
                    text = f"[{day}]"
                row_days.append(
                    InlineKeyboardButton(text=text, callback_data=f"cal_date_{year}_{month}_{day}")
                )
        markup.append(row_days)

    # 4. Кнопки действий
    row_actions = [
        InlineKeyboardButton(text="✅ Сегодня", callback_data="cal_today"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cal_cancel"),
    ]
    markup.append(row_actions)

    return InlineKeyboardMarkup(inline_keyboard=markup)


def get_schedule_dates_keyboard(
    dates_with_appointments: list[date],
    year: int,
    month: int
) -> InlineKeyboardMarkup:
    """Календарь-сетка для расписания: дни с записями кликабельны и выделены"""
    markup = []
    apt_days = {d.day for d in dates_with_appointments}

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    row_header = [
        InlineKeyboardButton(text="◀️", callback_data=f"sched_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text=f"{RU_MONTHS[month]} {year}", callback_data="sched_none"),
        InlineKeyboardButton(text="▶️", callback_data=f"sched_next_{next_year}_{next_month}"),
    ]
    markup.append(row_header)

    # Дни недели
    row_weekdays = [
        InlineKeyboardButton(text=day, callback_data="sched_none")
        for day in RU_WEEKDAYS
    ]
    markup.append(row_weekdays)

    # Сетка дней
    today = datetime.now().date()
    month_cal = cal_stdlib.monthcalendar(year, month)

    for week in month_cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="sched_none"))
            elif day in apt_days:
                # День с записями — кликабельный, выделен
                label = f"•{day}•" if date(year, month, day) == today else f"[{day}]"
                row.append(InlineKeyboardButton(
                    text=label,
                    callback_data=f"sched_date_{year}_{month}_{day}"
                ))
            else:
                # Обычный день без записей — не кликабельный
                label = f"·{day}·" if date(year, month, day) == today else str(day)
                row.append(InlineKeyboardButton(text=label, callback_data="sched_none"))
        markup.append(row)

    # Кнопка назад
    markup.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sched_back")])

    return InlineKeyboardMarkup(inline_keyboard=markup)


def get_time_slots_keyboard(
    start_hour: int = 9,
    end_hour: int = 18,
    slot_minutes: int = 30,
    selected_date: datetime | None = None,
    duration_minutes: int = 30,
    busy_ranges: list | None = None
) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени (слоты). busy_ranges — занятые интервалы [(start_dt, end_dt), ...]"""
    builder = InlineKeyboardBuilder()
    
    current_hour = start_hour
    current_minute = 0
    
    while current_hour < end_hour or (current_hour == end_hour and current_minute == 0):
        time_str = f"{current_hour:02d}:{current_minute:02d}"
        slot_available = True
        if busy_ranges and selected_date:
            slot_start = selected_date.replace(hour=current_hour, minute=current_minute, second=0, microsecond=0)
            slot_available = is_slot_available(slot_start, duration_minutes, busy_ranges)
        
        if slot_available:
            builder.button(text=time_str, callback_data=f"time_{time_str}")
        
        current_minute += slot_minutes
        if current_minute >= 60:
            current_minute = 0
            current_hour += 1
    
    builder.adjust(4)
    builder.button(text="❌ Отмена", callback_data="time_cancel")
    
    return builder.as_markup()

