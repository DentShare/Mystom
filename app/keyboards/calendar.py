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
    """Клавиатура с датами, в которых есть записи"""
    builder = InlineKeyboardBuilder()
    
    month_names = [
        "янв", "фев", "мар", "апр", "май", "июн",
        "июл", "авг", "сен", "окт", "ноя", "дек"
    ]
    
    for d in dates_with_appointments:
        text = f"{d.day} {month_names[d.month - 1]}"
        builder.button(
            text=text,
            callback_data=f"sched_date_{d.year}_{d.month}_{d.day}"
        )
    
    # Навигация по месяцам
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    
    builder.button(text="◀️", callback_data=f"sched_prev_{prev_year}_{prev_month}")
    builder.button(text=f"{month_names[month-1]} {year}", callback_data="sched_none")
    builder.button(text="▶️", callback_data=f"sched_next_{next_year}_{next_month}")
    builder.adjust(3)  # 3 кнопки в ряд для дат, навигация внизу
    
    builder.button(text="⬅️ Назад", callback_data="sched_back")
    
    return builder.as_markup()


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

