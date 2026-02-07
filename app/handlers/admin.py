from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import Config
from app.database.models import User

router = Router(name="admin")

TIER_NAMES = {0: "Basic", 1: "Standard", 2: "Premium"}


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
        "• /admin_set_tier telegram_id 0 или 1 или 2 — уровень без срока\n"
        "• /admin_set_subscription telegram_id tier дни — уровень и срок\n\n"
        "Уровни: 0=Basic, 1=Standard, 2=Premium.\n"
        "Telegram ID смотрите в списке пользователей."
    ).format(message.from_user.id)
    builder = InlineKeyboardBuilder()
    admin_webapp_url = getattr(Config, "ADMIN_WEBAPP_URL", None) or ""
    if admin_webapp_url.strip():
        builder.button(
            text="📱 Админка (Web App)",
            web_app=WebAppInfo(url=admin_webapp_url.strip())
        )
    builder.adjust(1)
    await message.answer(
        help_text,
        reply_markup=builder.as_markup() if admin_webapp_url.strip() else None,
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

