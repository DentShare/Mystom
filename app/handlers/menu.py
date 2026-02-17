from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database.models import User
from app.keyboards.main import get_main_menu_keyboard
from app.utils.constants import TIER_NAMES

router = Router(name="menu")


@router.message(Command("menu"))
@router.message(F.text == "⬅️ Назад в меню")
async def cmd_menu(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
):
    """Главное меню (у ассистента — контекст врача)."""
    await state.clear()
    tier_name = TIER_NAMES.get(effective_doctor.subscription_tier, "Basic")
    if getattr(user, "role", "owner") == "assistant" and user.owner_id:
        text = (
            f"📋 Главное меню\n\n"
            f"Вы: {user.full_name} (ассистент)\n"
            f"Врач: {effective_doctor.full_name}\n"
            f"⭐ Уровень подписки врача: {tier_name}\n\n"
            f"Выберите действие:"
        )
    else:
        text = (
            f"📋 Главное меню\n\n"
            f"👤 {user.full_name}\n"
            f"🏥 {user.specialization or 'Не указано'}\n"
            f"⭐ Уровень подписки: {tier_name}\n\n"
            f"Выберите действие:"
        )
    await message.answer(
        text,
        reply_markup=get_main_menu_keyboard(user, effective_doctor, assistant_permissions),
    )

