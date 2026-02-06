from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.database.models import User, Patient, Treatment, Appointment
from app.utils.formatters import format_money

router = Router(name="finance")


@router.message(F.text == "💰 Финансы", flags={'tier': 2})
async def cmd_finance(message: Message, user: User, db_session: AsyncSession):
    """Главное меню финансов"""
    # Подсчитываем статистику
    stmt = select(func.sum(Treatment.price).label("total"), func.count(Treatment.id).label("count")).where(
        Treatment.doctor_id == user.id
    )
    result = await db_session.execute(stmt)
    stats = result.first()
    
    total = stats.total or 0
    count = stats.count or 0
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="finance_stats")
    builder.button(text="💵 Оплаты", callback_data="finance_payments")
    builder.adjust(1)
    
    await message.answer(
        f"💰 **Финансовый модуль**\n\n"
        f"📈 Всего записей: {count}\n"
        f"💵 Общая сумма: {format_money(total)}\n\n"
        f"Выберите действие:",
        reply_markup=builder.as_markup()
    )

