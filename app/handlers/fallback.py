"""
Обработчик апдейтов, которые не попали ни в один другой хендлер.
Убирает "Update is not handled" и даёт пользователю подсказку.
"""
import logging
from aiogram import Router
from aiogram.types import Message, CallbackQuery

router = Router(name="fallback")
log = logging.getLogger("app.handlers.fallback")


@router.message()
async def fallback_message(message: Message):
    """Любое сообщение, не обработанное другими хендлерами (текст, стикер, голос и т.д.)."""
    log.debug("Необработанное сообщение: user_id=%s, content_type=%s", message.from_user.id if message.from_user else None, getattr(message, "content_type", None))
    await message.answer(
        "Не понимаю эту команду или тип сообщения. Используйте /menu или кнопки меню."
    )


@router.callback_query()
async def fallback_callback(callback: CallbackQuery):
    """Любой callback, не обработанный другими хендлерами (устаревшая кнопка и т.д.)."""
    log.debug("Необработанный callback: user_id=%s, data=%s", callback.from_user.id if callback.from_user else None, getattr(callback, "data", None))
    await callback.answer("Действие устарело. Обновите меню: /menu.", show_alert=False)
