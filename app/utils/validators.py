"""Валидаторы для проверки данных"""
import re
from datetime import datetime, date


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

