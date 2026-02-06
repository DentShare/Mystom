from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database.models import User
from app.keyboards.main import get_main_menu_keyboard

router = Router(name="menu")


@router.message(Command("menu"))
@router.message(F.text == "⬅️ Назад в меню")
async def cmd_menu(message: Message, user: User, state: FSMContext):
    """Главное меню"""
    await state.clear()
    tier_names = {0: "Basic", 1: "Standard", 2: "Premium"}
    tier_name = tier_names.get(user.subscription_tier, "Basic")
    
    text = (
        f"📋 Главное меню\n\n"
        f"👤 {user.full_name}\n"
        f"🏥 {user.specialization or 'Не указано'}\n"
        f"⭐ Уровень подписки: {tier_name}\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(
        text,
        reply_markup=get_main_menu_keyboard(user)
    )

