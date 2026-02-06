"""Форматирование текста"""
from datetime import datetime, date

# Валюта: узбекские сумы (UZS)
CURRENCY = "сум"


def format_date(dt: datetime | date) -> str:
    """Форматирование даты"""
    if isinstance(dt, datetime):
        return dt.strftime("%d.%m.%Y %H:%M")
    return dt.strftime("%d.%m.%Y")


def format_money(amount: float, decimals: int = 0) -> str:
    """Форматирование денежной суммы в узбекских сумах"""
    if decimals == 0:
        return f"{amount:,.0f} {CURRENCY}".replace(",", " ")
    return f"{amount:,.2f} {CURRENCY}".replace(",", " ")


def format_patient_name(patient) -> str:
    """Форматирование имени пациента"""
    return f"{patient.full_name} ({patient.phone or 'нет телефона'})"


def treatment_effective_price(price: float | None, discount_percent: float | None, discount_amount: float | None) -> float:
    """Итоговая цена услуги с учётом скидки (процент и/или сумма)."""
    if price is None:
        return 0.0
    p = float(price)
    if discount_percent is not None:
        p = p * (1 - discount_percent / 100)
    if discount_amount is not None:
        p = p - discount_amount
    return max(0.0, round(p, 2))

