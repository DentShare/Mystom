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
from app.middleware.throttle import ThrottleMiddleware
from app.middleware.user import UserMiddleware
from app.middleware.subscription import SubscriptionMiddleware

# Импорты роутеров
from app.handlers import start, menu, settings, business_card, calendar, patients, history, implant, finance, services, admin, export, subscription, team, voice_booking, fallback
from app.services.reminder_service import (
    get_appointments_due_for_reminder,
    format_reminder_message,
)
from app.services.error_monitor import error_monitor

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
    _url = (getattr(Config, "ADMIN_WEBAPP_URL", None) or "").strip()
    if _url:
        try:
            from urllib.parse import urlparse
            _host = urlparse(_url).netloc or _url[:50]
        except Exception:
            _host = _url[:50]
        logger.info("ADMIN_WEBAPP_URL для кнопки админки: host=%s", _host)
    else:
        logger.warning("ADMIN_WEBAPP_URL не задан — кнопка «Админка (Web App)» не будет показана")

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
    dp.message.middleware(ThrottleMiddleware(rate=5, period=10))
    dp.callback_query.middleware(ThrottleMiddleware(rate=10, period=10))
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
    dp.include_router(team.router)
    dp.include_router(admin.router)
    dp.include_router(voice_booking.router)  # голос/фото запись (до fallback!)
    dp.include_router(fallback.router)  # последним — ловит всё необработанное

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        """Глобальный обработчик ошибок: логирование, ответ пользователю, отчёт админам."""
        logger.exception("Ошибка при обработке апдейта: %s", event.exception)

        # Извлекаем контекст для отчёта
        user_id = None
        handler_name = ""
        try:
            update = event.update
            if update.message and update.message.from_user:
                user_id = update.message.from_user.id
                handler_name = f"message: {(update.message.text or '')[:50]}"
            elif update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
                handler_name = f"callback: {update.callback_query.data or ''}"
        except Exception:
            pass

        # Отправляем отчёт админам (асинхронно, не блокируя ответ пользователю)
        asyncio.create_task(
            error_monitor.report(
                event.exception,
                handler=handler_name,
                user_id=user_id,
            )
        )

        # Ответ пользователю
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

    # Запуск мониторинга ошибок
    await error_monitor.start(bot)

    async def run_reminders():
        """Фоновая задача: проверка и отправка напоминаний каждые 60 сек"""
        from sqlalchemy import select as sa_select
        from app.database.models import DoctorAssistant, User as UserModel

        while True:
            try:
                await asyncio.sleep(60)
                async with async_session_maker() as db_session:
                    due = await get_appointments_due_for_reminder(db_session)
                    for apt, doctor, reminder_mins in due:
                        try:
                            text = format_reminder_message(apt, reminder_mins)

                            # Собираем получателей: врач + ассистенты
                            recipients = {doctor.telegram_id}
                            assistants_stmt = (
                                sa_select(UserModel.telegram_id)
                                .join(DoctorAssistant, DoctorAssistant.assistant_id == UserModel.id)
                                .where(DoctorAssistant.doctor_id == doctor.id)
                            )
                            result = await db_session.execute(assistants_stmt)
                            for (tid,) in result.all():
                                recipients.add(tid)

                            for tid in recipients:
                                try:
                                    await bot.send_message(tid, text)
                                except Exception as e:
                                    logger.warning("Reminder send error to %s: %s", tid, e)
                                await asyncio.sleep(0.05)

                            apt.reminder_sent_at = datetime.now()
                            logger.info("Reminder sent for appointment %s to %d recipients", apt.id, len(recipients))
                        except Exception as e:
                            logger.exception("Reminder send error: %s", e)
                            await error_monitor.report(e, context="reminder: отправка напоминания")
                    # Один commit на всю пачку вместо коммита на каждое напоминание
                    await db_session.commit()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Reminder scheduler error: %s", e)
                await error_monitor.report(e, context="reminder: цикл планировщика")

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
        await error_monitor.stop()
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

