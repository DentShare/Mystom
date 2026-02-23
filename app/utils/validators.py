"""Валидаторы для проверки данных"""
import re
from datetime import datetime, date

# Лимиты длины строк
MAX_NAME_LENGTH = 100
MAX_SPECIALIZATION_LENGTH = 100
MAX_ADDRESS_LENGTH = 500
MAX_NOTES_LENGTH = 2000
MAX_SERVICE_NAME_LENGTH = 200


def validate_phone(phone: str) -> bool:
    """Валидация телефона"""
    if not phone:
        return False
    # Простая проверка: минимум 10 цифр
    digits = re.sub(r'\D', '', phone)
    return len(digits) >= 10


def validate_date(date_str: str, format_str: str = "%d.%m.%Y") -> bool:
    """Валидация даты"""
    try:
        datetime.strptime(date_str, format_str)
        return True
    except ValueError:
        return False


def validate_tooth_number(tooth: str) -> bool:
    """Валидация номера зуба"""
    if not tooth:
        return False
    # Проверка формата: 11-48 или моляры 51-85
    try:
        num = int(tooth)
        return (11 <= num <= 48) or (51 <= num <= 85)
    except ValueError:
        return False


def validate_price(price: str) -> bool:
    """Валидация цены"""
    try:
        value = float(price)
        return value >= 0
    except ValueError:
        return False


def validate_string_length(text: str, min_len: int = 1, max_len: int = 255) -> bool:
    """Проверка длины строки в допустимых пределах."""
    return min_len <= len(text.strip()) <= max_len

