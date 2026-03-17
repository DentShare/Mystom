import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import Config
from app.database.models import User
from app.services.user_service import delete_user_from_db
from app.utils.constants import TIER_NAMES
router = Router(name="admin")
_admin_log = logging.getLogger("app.handlers.admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in Config.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Меню админа: справка и кнопка Web App"""
    if not message.from_user:
        return
    if message.from_user.id not in Config.ADMIN_IDS:
        await message.answer(
            "❌ Доступ запрещён. Ваш Telegram ID: {}. "
            "Добавьте его в переменную ADMIN_IDS в настройках бота (Railway → Variables).".format(
                message.from_user.id
            ),
            parse_mode=None,
        )
        return

    # Без parse_mode: символы < > | и разметка ломают парсер Telegram
    help_text = (
        "🛠 Админ-панель\n\n"
        "Ваш ID: {} (должен быть в ADMIN_IDS)\n\n"
        "Команды:\n"
        "• /admin_list_users — список пользователей\n"
        "• /admin_delete_user telegram_id — удалить пользователя (сможет заново /start)\n"
        "• /admin_set_tier telegram_id 0|1|2 — уровень без срока\n"
        "• /admin_set_subscription telegram_id tier дни — уровень и срок\n"
        "• /admin_send telegram_id текст — личное сообщение пользователю\n"
        "• /admin_broadcast текст — сообщение всем пользователям\n"
        "• /errors — статистика ошибок мониторинга\n\n"
        "Уровни: 0=Basic, 1=Standard, 2=Premium.\n"
        "Telegram ID смотрите в списке пользователей."
    ).format(message.from_user.id)
    builder = InlineKeyboardBuilder()
    admin_webapp_url = getattr(Config, "ADMIN_WEBAPP_URL", None) or ""
    admin_webapp_url = admin_webapp_url.strip()
    # Лог для отладки: на какой URL ведёт кнопка (в Railway должен совпадать с доменом этого сервиса)
    if admin_webapp_url:
        try:
            from urllib.parse import urlparse
            host = urlparse(admin_webapp_url).netloc or "(не удалось разобрать)"
        except Exception:
            host = "(ошибка разбора URL)"
        _admin_log.info("Кнопка «Админка (Web App)»: ADMIN_WEBAPP_URL → host=%s", host)
    if admin_webapp_url:
        builder.button(
            text="📱 Админка (Web App)",
            web_app=WebAppInfo(url=admin_webapp_url)
        )
    builder.adjust(1)
    await message.answer(
        help_text,
        reply_markup=builder.as_markup() if admin_webapp_url else None,
        parse_mode=None,
    )


@router.message(Command("admin_set_tier", "adminsettier"))
async def cmd_set_tier(message: Message, db_session: AsyncSession):
    """Установка уровня подписки"""
    if message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /admin_set_tier <user_id> <tier>")
        return
    
    try:
        user_id = int(args[1])
        tier = int(args[2])
        
        if tier not in [0, 1, 2]:
            await message.answer("❌ Уровень должен быть 0 (Basic), 1 (Standard) или 2 (Premium)")
            return
        
        stmt = select(User).where(User.telegram_id == user_id)
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            return
        
        user.subscription_tier = tier
        user.subscription_end_date = None  # бессрочно при set_tier
        await db_session.commit()
        await message.answer(
            f"✅ Уровень подписки установлен!\n\n"
            f"Пользователь: {user.full_name}\n"
            f"Telegram ID: {user.telegram_id}\n"
            f"Уровень: {TIER_NAMES[tier]}"
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /admin_set_tier <telegram_id> <tier>")


@router.message(Command("admin_set_subscription", "adminsetsubscription"))
async def cmd_set_subscription(message: Message, db_session: AsyncSession):
    """Установка подписки на N дней"""
    if message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    args = message.text.split()
    if len(args) < 4:
        await message.answer("Использование: /admin_set_subscription <user_id> <tier> <days>")
        return
    
    try:
        user_id = int(args[1])
        tier = int(args[2])
        days = int(args[3])
        
        if tier not in [0, 1, 2]:
            await message.answer("❌ Уровень должен быть 0 (Basic), 1 (Standard) или 2 (Premium)")
            return
        
        stmt = select(User).where(User.telegram_id == user_id)
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            return
        
        user.subscription_tier = tier
        user.subscription_end_date = datetime.now() + timedelta(days=days)
        await db_session.commit()
        await message.answer(
            f"✅ Подписка установлена!\n\n"
            f"Пользователь: {user.full_name}\n"
            f"Telegram ID: {user.telegram_id}\n"
            f"Уровень: {TIER_NAMES[tier]}\n"
            f"Действует до: {user.subscription_end_date.strftime('%d.%m.%Y')}"
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /admin_set_subscription <telegram_id> <tier> <days>")


@router.message(Command("admin_delete_user", "admindeleteuser"))
async def cmd_delete_user(message: Message, db_session: AsyncSession):
    """Удалить пользователя по telegram_id. Он сможет заново нажать /start и пройти регистрацию."""
    if message.from_user and message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "Использование: /admin_delete_user <telegram_id>\n"
            "Пример: /admin_delete_user 123456789\n"
            "Пользователь будет удалён из БД (все его данные: пациенты, записи и т.д.). "
            "После этого он может снова нажать /start и зарегистрироваться.",
            parse_mode=None,
        )
        return

    try:
        telegram_id = int(args[1])
    except ValueError:
        await message.answer("❌ telegram_id должен быть числом.")
        return

    if telegram_id in Config.ADMIN_IDS:
        await message.answer("❌ Нельзя удалить администратора (его ID в ADMIN_IDS).", parse_mode=None)
        return

    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        await message.answer(f"❌ Пользователь с ID {telegram_id} не найден.")
        return

    name = (user.full_name or "").strip() or "—"
    ok = await delete_user_from_db(db_session, user)
    if ok:
        await message.answer(
            f"✅ Пользователь {name} (ID: {telegram_id}) удалён.\n"
            "Он может снова нажать /start в боте и пройти регистрацию.",
            parse_mode=None,
        )
    else:
        await message.answer("❌ Не удалось удалить пользователя.")


@router.message(Command("admin_list_users", "adminlistusers"))
async def cmd_list_users(message: Message, db_session: AsyncSession):
    """Список всех пользователей с уровнем и сроком подписки"""
    if message.from_user and message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return

    stmt = select(User).order_by(User.created_at.desc()).limit(50)
    result = await db_session.execute(stmt)
    users = list(result.scalars().all())

    if not users:
        await message.answer("📋 Пользователей нет")
        return

    # Без parse_mode: имена пользователей могут содержать _ * [ и ломать Markdown
    text_parts = ["📋 Список пользователей (для команд используйте telegram_id):\n"]
    for u in users:
        tier_name = TIER_NAMES.get(u.subscription_tier, "Basic")
        end = f", до {u.subscription_end_date.strftime('%d.%m.%Y')}" if u.subscription_end_date else ", без срока"
        name = (u.full_name or "").strip() or "—"
        text_parts.append(f"👤 {name}\n   ID: {u.telegram_id} · {tier_name}{end}\n")
    await message.answer("\n".join(text_parts), parse_mode=None)


@router.message(Command("admin_send", "adminsend"))
async def cmd_admin_send(message: Message, db_session: AsyncSession):
    """Отправить личное сообщение пользователю по telegram_id."""
    if message.from_user and message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return

    args = message.text.split(maxsplit=2)  # команда, telegram_id, остальное — текст
    if len(args) < 3:
        await message.answer(
            "Использование: /admin_send <telegram_id> <текст>\n"
            "Пример: /admin_send 123456789 Добрый день! Напоминаем о записи.",
            parse_mode=None,
        )
        return

    try:
        target_id = int(args[1])
        text = args[2].strip()
    except ValueError:
        await message.answer("❌ telegram_id должен быть числом.")
        return

    if not text:
        await message.answer("❌ Текст сообщения не может быть пустым.")
        return

    # Проверяем, что пользователь есть в БД (опционально; можно слать и не из БД)
    stmt = select(User).where(User.telegram_id == target_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one_or_none()

    try:
        await message.bot.send_message(chat_id=target_id, text=text, parse_mode=None)
        name = (user.full_name or "").strip() if user else "—"
        await message.answer(
            f"✅ Сообщение отправлено пользователю {name} (ID: {target_id}).",
            parse_mode=None,
        )
    except Exception as e:
        await message.answer(
            f"❌ Не удалось отправить (возможно, пользователь заблокировал бота или чат удалён): {e!r}",
            parse_mode=None,
        )


@router.message(Command("admin_broadcast", "adminbroadcast"))
async def cmd_admin_broadcast(message: Message, db_session: AsyncSession):
    """Разослать сообщение всем пользователям из БД."""
    if message.from_user and message.from_user.id not in Config.ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return

    text = message.text.split(maxsplit=1)[-1].strip() if message.text else ""
    if not text:
        await message.answer(
            "Использование: /admin_broadcast <текст>\n"
            "Всё после команды будет отправлено всем пользователям.",
            parse_mode=None,
        )
        return

    stmt = select(User).distinct(User.telegram_id)
    result = await db_session.execute(stmt)
    users = list(result.scalars().all())

    # Не слать админам; пропускать opt-out
    admin_ids_set = set(Config.ADMIN_IDS)
    to_send = []
    skipped = 0
    for u in users:
        if u.telegram_id in admin_ids_set:
            continue
        if (u.settings or {}).get("broadcast_opt_out"):
            skipped += 1
            continue
        to_send.append(u.telegram_id)

    if not to_send:
        await message.answer("📋 Нет пользователей для рассылки (кроме админов).")
        return

    sent = 0
    failed = 0
    status_msg = await message.answer(f"📤 Рассылка: {len(to_send)} получателей…")
    for uid in to_send:
        try:
            await message.bot.send_message(chat_id=uid, text=text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Telegram rate-limit: не более 30 msg/sec

    extra = f", пропущено (opt-out): {skipped}" if skipped else ""
    await status_msg.edit_text(
        f"✅ Рассылка завершена.\nОтправлено: {sent}, не доставлено: {failed}{extra}.",
        parse_mode=None,
    )


@router.message(Command("errors"))
async def cmd_errors(message: Message):
    """Статистика мониторинга ошибок (только для админов)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    from app.services.error_monitor import error_monitor
    stats = await error_monitor.get_stats()
    await message.answer(stats, parse_mode="HTML")

