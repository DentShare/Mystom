from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from app.database.models import User
from app.utils.permissions import (
    can_access,
    FEATURE_CALENDAR,
    FEATURE_PATIENTS,
    FEATURE_HISTORY,
    FEATURE_IMPLANTS,
    FEATURE_SERVICES,
    FEATURE_FINANCE,
    FEATURE_EXPORT,
    FEATURE_SETTINGS,
)


def get_main_menu_keyboard(
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
) -> ReplyKeyboardMarkup:
    """Главное меню: по подписке врача (effective_doctor) и правам ассистента."""
    builder = ReplyKeyboardBuilder()
    tier = effective_doctor.subscription_tier

    if can_access(assistant_permissions, FEATURE_CALENDAR):
        builder.button(text="📅 Календарь")
        builder.button(text="📋 Расписание")
    builder.button(text="👤 Визитка")
    if can_access(assistant_permissions, FEATURE_SERVICES):
        builder.button(text="💵 Прайс-лист")

    if tier >= 1:
        if can_access(assistant_permissions, FEATURE_PATIENTS):
            builder.button(text="👥 Пациенты")
        if can_access(assistant_permissions, FEATURE_HISTORY):
            builder.button(text="📋 История болезни")
    if tier >= 1 and can_access(assistant_permissions, FEATURE_IMPLANTS):
        builder.button(text="🦷 Импланты")

    if tier >= 2:
        if can_access(assistant_permissions, FEATURE_FINANCE):
            builder.button(text="💰 Финансы")
        if can_access(assistant_permissions, FEATURE_EXPORT):
            builder.button(text="📊 Экспорт")

    builder.button(text="⭐ Подписка")
    if can_access(assistant_permissions, FEATURE_SETTINGS):
        builder.button(text="⚙️ Настройки")
    builder.button(text="👥 Моя команда")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура настроек"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="⬅️ Назад в меню")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

