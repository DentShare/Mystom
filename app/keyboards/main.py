from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from app.database.models import User


def get_main_menu_keyboard(user: User) -> ReplyKeyboardMarkup:
    """Главное меню в зависимости от уровня подписки"""
    builder = ReplyKeyboardBuilder()
    
    # Базовые функции (доступны всем)
    builder.button(text="📅 Календарь")
    builder.button(text="📋 Расписание")
    builder.button(text="👤 Визитка")
    builder.button(text="💵 Прайс-лист")  # Просмотр для всех, редактирование — Premium
    
    # Стандартные функции (tier >= 1)
    if user.subscription_tier >= 1:
        builder.button(text="👥 Пациенты")
        builder.button(text="📋 История болезни")
    
    # Премиум функции (tier >= 2)
    if user.subscription_tier >= 2:
        builder.button(text="💰 Финансы")
        builder.button(text="📊 Экспорт")
    
    builder.button(text="⭐ Подписка")
    builder.button(text="⚙️ Настройки")
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

