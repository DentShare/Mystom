"""Экспорт базы пациентов в Excel (Premium)."""
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.services.export_service import get_patients_with_relations, build_patients_excel

router = Router(name="export")


@router.message(F.text == "📊 Экспорт", flags={"tier": 2})
async def cmd_export(message: Message, user: User, db_session: AsyncSession):
    """Выгрузка базы пациентов со всеми данными в Excel (Premium)."""
    await message.answer("⏳ Формирую выгрузку…")
    try:
        patients = await get_patients_with_relations(db_session, user.id)
        if not patients:
            await message.answer(
                "📋 У вас пока нет пациентов.\n"
                "Добавьте пациентов в разделе «👥 Пациенты», затем повторите экспорт."
            )
            return
        buf = build_patients_excel(patients)
        filename = f"patients_export_{message.from_user.id if message.from_user else 0}.xlsx"
        file = BufferedInputFile(buf.read(), filename=filename)
        await message.answer_document(
            document=file,
            caption=(
                f"📊 **Экспорт базы пациентов**\n\n"
                f"👥 Пациентов: {len(patients)}\n"
                f"Листы: Пациенты, Записи на приём, История лечения, Импланты"
            ),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при формировании выгрузки: {e}")
