import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.config import Config
from app.database.base import init_db, close_db, async_session_maker
from app.middleware.user import UserMiddleware
from app.middleware.subscription import SubscriptionMiddleware

# Импорты роутеров
from app.handlers import start, menu, settings, business_card, calendar, patients, history, implant, finance, services, admin, export, subscription
from app.services.reminder_service import (
    get_appointments_due_for_reminder,
    format_reminder_message,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    # Валидация конфигурации
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        return

    # Для сверки с админкой: тот же BOT_TOKEN должен быть в сервисе админки
    _t = Config.BOT_TOKEN
    _mask = f"{_t[:8]}...{_t[-4:]} (len={len(_t)})" if _t and len(_t) >= 12 else "(короткий)"
    logger.info("BOT_TOKEN для сверки с админкой: %s", _mask)

    # Инициализация БД
    try:
        await init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return
    
    # Создание бота и диспетчера
    bot = Bot(
        token=Config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация middleware
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(settings.router)
    dp.include_router(business_card.router)
    dp.include_router(calendar.router)
    dp.include_router(patients.router)
    dp.include_router(history.router)
    dp.include_router(implant.router)
    dp.include_router(finance.router)
    dp.include_router(services.router)
    dp.include_router(export.router)
    dp.include_router(subscription.router)
    dp.include_router(admin.router)

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        """Глобальный обработчик ошибок: логирование и ответ пользователю."""
        logger.exception("Ошибка при обработке апдейта: %s", event.exception)
        try:
            update = event.update
            if update.message:
                await update.message.answer(
                    "⚠️ Произошла временная ошибка. Попробуйте позже или начните с /menu."
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    "Ошибка. Попробуйте ещё раз.",
                    show_alert=False
                )
                if update.callback_query.message:
                    await update.callback_query.message.answer(
                        "⚠️ Произошла временная ошибка. Попробуйте снова или /menu."
                    )
        except Exception as e:
            logger.exception("Не удалось отправить сообщение об ошибке пользователю: %s", e)
        return True

    logger.info("Бот запущен")

    async def run_reminders():
        """Фоновая задача: проверка и отправка напоминаний каждые 60 сек"""
        while True:
            try:
                await asyncio.sleep(60)
                async with async_session_maker() as db_session:
                    due = await get_appointments_due_for_reminder(db_session)
                    for apt, doctor, reminder_mins in due:
                        try:
                            text = format_reminder_message(apt, reminder_mins)
                            await bot.send_message(doctor.telegram_id, text)
                            apt.reminder_sent_at = datetime.now()
                            await db_session.commit()
                            logger.info(f"Reminder sent for appointment {apt.id} to doctor {doctor.id}")
                        except Exception as e:
                            logger.exception(f"Reminder send error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Reminder scheduler error: {e}")

    reminder_task = asyncio.create_task(run_reminders())

    # Запуск polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

