from typing import Optional
import pytz


def get_timezone_by_name(timezone_name: str) -> Optional[pytz.BaseTzInfo]:
    """Получить объект часового пояса по названию"""
    try:
        return pytz.timezone(timezone_name)
    except pytz.exceptions.UnknownTimeZoneError:
        return None


def get_common_timezones() -> list[tuple[str, str]]:
    """Получить список популярных часовых поясов"""
    return [
        ("Europe/Moscow", "Москва (UTC+3)"),
        ("Europe/Kiev", "Киев (UTC+2)"),
        ("Europe/Minsk", "Минск (UTC+3)"),
        ("Asia/Almaty", "Алматы (UTC+6)"),
        ("Asia/Tashkent", "Ташкент (UTC+5)"),
        ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
        ("Asia/Krasnoyarsk", "Красноярск (UTC+7)"),
        ("Asia/Irkutsk", "Иркутск (UTC+8)"),
        ("Asia/Vladivostok", "Владивосток (UTC+10)"),
    ]

