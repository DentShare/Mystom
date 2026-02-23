from datetime import date
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import User, Patient, ImplantLog
from app.states.implant import ImplantStates
from app.utils.permissions import can_access, FEATURE_IMPLANTS
from app.keyboards.implant import (
    get_tooth_chart_keyboard,
    get_implant_systems_keyboard,
    get_diameter_keyboard,
    get_length_keyboard,
)

router = Router(name="implant")


def _format_existing_implants(implants: list) -> str:
    """Форматирование списка уже добавленных имплантов"""
    if not implants:
        return ""
    lines = ["**Уже добавленные импланты:**"]
    for imp in implants:
        date_str = imp.operation_date.strftime("%d.%m.%Y") if imp.operation_date else "—"
        size_str = imp.implant_size or "—"
        lines.append(f"  • Зуб {imp.tooth_number} — {imp.system_name} ({size_str}), {date_str}")
    return "\n".join(lines) + "\n\n"


@router.callback_query(F.data.startswith("implant_add_"), flags={"tier": 1})
async def start_add_implant(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    """Начало добавления импланта (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_IMPLANTS, "edit"):
        await callback.answer("Нет доступа к добавлению имплантов.", show_alert=True)
        return
    patient_id = int(callback.data.replace("implant_add_", ""))

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    stmt = select(ImplantLog).where(
        and_(
            ImplantLog.patient_id == patient_id,
            ImplantLog.doctor_id == effective_doctor.id
        )
    ).order_by(ImplantLog.operation_date)
    result = await db_session.execute(stmt)
    existing_implants = list(result.scalars().all())

    existing_text = _format_existing_implants(existing_implants)
    await state.update_data(implant_patient_id=patient_id, implant_selected_teeth=[])
    await callback.message.edit_text(
        "🔩 **Добавление импланта**\n\n"
        + existing_text +
        "Выберите зубы (можно несколько). Нажмите на зуб для выбора/снятия.\n"
        "Затем нажмите «✓ Подтвердить выбор»:",
        reply_markup=get_tooth_chart_keyboard([])
    )
    await callback.answer()
    await state.set_state(ImplantStates.select_teeth)


@router.callback_query(StateFilter(ImplantStates.select_teeth), F.data.startswith("tooth_t_"))
async def process_tooth_toggle(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора зуба"""
    tooth = int(callback.data.replace("tooth_t_", ""))
    data = await state.get_data()
    selected: list = data.get("implant_selected_teeth", []).copy()

    if tooth in selected:
        selected.remove(tooth)
    else:
        selected.append(tooth)
    selected.sort()

    await state.update_data(implant_selected_teeth=selected)
    await callback.message.edit_reply_markup(reply_markup=get_tooth_chart_keyboard(selected))
    await callback.answer()


@router.callback_query(StateFilter(ImplantStates.select_teeth), F.data == "tooth_confirm")
async def process_tooth_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора зубов"""
    data = await state.get_data()
    selected = data.get("implant_selected_teeth", [])

    if not selected:
        await callback.answer("❌ Выберите хотя бы один зуб", show_alert=True)
        return

    teeth_str = ", ".join(map(str, selected))
    await callback.message.edit_text(
        f"✅ Выбраны зубы: **{teeth_str}**\n\n"
        "Выберите компанию/систему импланта:",
        reply_markup=get_implant_systems_keyboard()
    )
    await state.set_state(ImplantStates.select_system)
    await callback.answer()


@router.callback_query(StateFilter(ImplantStates.select_teeth), F.data == "tooth_manual")
async def process_tooth_manual_start(callback: CallbackQuery, state: FSMContext):
    """Ручной ввод номеров зубов"""
    await callback.message.edit_text(
        "✍️ Введите номера зубов через запятую или пробел (например: 36, 37, 46):"
    )
    await callback.answer()


@router.message(StateFilter(ImplantStates.select_teeth), F.text)
async def process_tooth_manual_input(message: Message, state: FSMContext):
    """Обработка ручного ввода зубов"""
    parts = [p.strip() for p in message.text.replace(",", " ").split() if p.strip()]
    selected = []
    for p in parts:
        try:
            n = int(p)
            if 11 <= n <= 18 or 21 <= n <= 28 or 31 <= n <= 38 or 41 <= n <= 48:
                selected.append(n)
        except ValueError:
            pass
    selected = sorted(set(selected))

    if not selected:
        await message.answer("❌ Введите корректные номера зубов (11-48):")
        return

    await state.update_data(implant_selected_teeth=selected)
    teeth_str = ", ".join(map(str, selected))
    await message.answer(
        f"✅ Выбраны зубы: **{teeth_str}**\n\n"
        "Выберите компанию/систему импланта:",
        reply_markup=get_implant_systems_keyboard()
    )
    await state.set_state(ImplantStates.select_system)


@router.callback_query(F.data == "implant_cancel")
async def implant_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления импланта (из любого состояния)"""
    await callback.message.delete()
    await state.clear()
    await callback.answer("❌ Отменено")


# Система
@router.callback_query(StateFilter(ImplantStates.select_system), F.data.startswith("system_"))
async def process_system_selection(callback: CallbackQuery, state: FSMContext):
    if callback.data == "system_custom":
        await callback.message.edit_text("✍️ Введите название компании/системы импланта:")
        await state.set_state(ImplantStates.enter_system)
        await callback.answer()
        return

    system_name = callback.data.replace("system_", "")
    await state.update_data(implant_system_name=system_name)
    await callback.message.edit_text(
        f"✅ Система: **{system_name}**\n\n"
        "Выберите диаметр импланта (мм):",
        reply_markup=get_diameter_keyboard()
    )
    await state.set_state(ImplantStates.select_diameter)
    await callback.answer()


@router.message(StateFilter(ImplantStates.enter_system), F.text)
async def process_system_manual(message: Message, state: FSMContext):
    system_name = message.text.strip()
    if len(system_name) < 2 or len(system_name) > 255:
        await message.answer("❌ Введите корректное название (2-255 символов):")
        return

    await state.update_data(implant_system_name=system_name)
    await message.answer(
        f"✅ Система: **{system_name}**\n\n"
        "Выберите диаметр импланта (мм):",
        reply_markup=get_diameter_keyboard()
    )
    await state.set_state(ImplantStates.select_diameter)


# Диаметр
@router.callback_query(StateFilter(ImplantStates.select_diameter), F.data.startswith("diam_"))
async def process_diameter_selection(callback: CallbackQuery, state: FSMContext):
    if callback.data == "diam_manual":
        await callback.message.edit_text("✍️ Введите диаметр в мм (например: 4.0):")
        await state.set_state(ImplantStates.enter_diameter)
        await callback.answer()
        return

    diameter = float(callback.data.replace("diam_", ""))
    await state.update_data(implant_diameter=diameter)
    await callback.message.edit_text(
        f"✅ Диаметр: **{diameter} мм**\n\n"
        "Выберите длину импланта (мм):",
        reply_markup=get_length_keyboard()
    )
    await state.set_state(ImplantStates.select_length)
    await callback.answer()


@router.message(StateFilter(ImplantStates.enter_diameter), F.text)
async def process_diameter_manual(message: Message, state: FSMContext):
    try:
        diameter = float(message.text.strip().replace(",", "."))
        if not (3.0 <= diameter <= 8.0):
            raise ValueError("Диаметр от 3 до 8 мм")
    except ValueError:
        await message.answer("❌ Введите число от 3.0 до 8.0:")
        return

    await state.update_data(implant_diameter=diameter)
    await message.answer(
        f"✅ Диаметр: **{diameter} мм**\n\n"
        "Выберите длину импланта (мм):",
        reply_markup=get_length_keyboard()
    )
    await state.set_state(ImplantStates.select_length)


# Длина
@router.callback_query(StateFilter(ImplantStates.select_length), F.data.startswith("len_"))
async def process_length_selection(callback: CallbackQuery, state: FSMContext):
    if callback.data == "len_manual":
        await callback.message.edit_text("✍️ Введите длину в мм (например: 10):")
        await state.set_state(ImplantStates.enter_length)
        await callback.answer()
        return

    length = float(callback.data.replace("len_", ""))
    await state.update_data(implant_length=length)
    await callback.message.edit_text(
        f"✅ Длина: **{length} мм**\n\n"
        "Введите дополнительные заметки (или /skip для пропуска):"
    )
    await state.set_state(ImplantStates.enter_notes)
    await callback.answer()


@router.message(StateFilter(ImplantStates.enter_length), F.text)
async def process_length_manual(message: Message, state: FSMContext):
    try:
        length = float(message.text.strip().replace(",", "."))
        if not (7 <= length <= 18):
            raise ValueError("Длина от 7 до 18 мм")
    except ValueError:
        await message.answer("❌ Введите число от 7 до 18:")
        return

    await state.update_data(implant_length=length)
    await message.answer(
        f"✅ Длина: **{length} мм**\n\n"
        "Введите дополнительные заметки (или /skip для пропуска):"
    )
    await state.set_state(ImplantStates.enter_notes)


# Заметки и сохранение
@router.message(StateFilter(ImplantStates.enter_notes), F.text)
async def process_implant_notes(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_IMPLANTS, "edit"):
        await message.answer("🚫 Недостаточно прав для добавления имплантов.")
        await state.clear()
        return
    notes = None
    if message.text and message.text.strip().lower() != "/skip":
        notes = message.text.strip()

    data = await state.get_data()
    patient_id = data.get("implant_patient_id")
    selected_teeth = data.get("implant_selected_teeth", [])
    system_name = data.get("implant_system_name")
    diameter = data.get("implant_diameter")
    length = data.get("implant_length")

    implant_size = f"{diameter} x {length}"

    for tooth in selected_teeth:
        implant = ImplantLog(
            patient_id=patient_id,
            doctor_id=effective_doctor.id,
            tooth_number=str(tooth),
            system_name=system_name,
            implant_size=implant_size,
            notes=notes,
            operation_date=date.today()
        )
        db_session.add(implant)
    await db_session.commit()

    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db_session.execute(stmt)
    patient = result.scalar_one()

    teeth_str = ", ".join(map(str, selected_teeth))
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ещё имплант", callback_data=f"implant_add_{patient_id}")
    builder.button(text="✅ Завершить планирование", callback_data=f"implant_done_{patient_id}")
    builder.adjust(1)

    await message.answer(
        f"✅ Импланты добавлены!\n\n"
        f"👤 Пациент: {patient.full_name}\n"
        f"🦷 Зубы: {teeth_str}\n"
        f"🔩 Система: {system_name}\n"
        f"📏 Размер: {implant_size} мм\n"
        f"📅 Дата: {date.today().strftime('%d.%m.%Y')}\n\n"
        f"Добавить ещё или завершить?",
        reply_markup=builder.as_markup()
    )
    await state.set_state(ImplantStates.add_more)
    await state.update_data(implant_patient_id=patient_id)


@router.callback_query(StateFilter(ImplantStates.add_more), F.data.startswith("implant_add_"))
async def implant_add_more(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_IMPLANTS, "edit"):
        await callback.answer("🚫 Недостаточно прав для добавления имплантов.", show_alert=True)
        await state.clear()
        return
    """Добавить ещё имплант — возврат к карте зубов (данные врача)."""
    patient_id = int(callback.data.replace("implant_add_", ""))
    stmt = select(ImplantLog).where(
        and_(
            ImplantLog.patient_id == patient_id,
            ImplantLog.doctor_id == effective_doctor.id
        )
    ).order_by(ImplantLog.operation_date)
    result = await db_session.execute(stmt)
    existing_implants = list(result.scalars().all())

    existing_text = _format_existing_implants(existing_implants)
    await state.update_data(implant_patient_id=patient_id, implant_selected_teeth=[])
    await callback.message.edit_text(
        "🔩 **Добавление импланта**\n\n"
        + existing_text +
        "Выберите зубы (можно несколько). Нажмите «✓ Подтвердить выбор»:",
        reply_markup=get_tooth_chart_keyboard([])
    )
    await state.set_state(ImplantStates.select_teeth)
    await callback.answer()


@router.callback_query(StateFilter(ImplantStates.add_more), F.data.startswith("implant_done_"))
async def implant_done(callback: CallbackQuery, assistant_permissions: dict, state: FSMContext, db_session: AsyncSession):
    if not can_access(assistant_permissions, FEATURE_IMPLANTS):
        await callback.answer("🚫 Нет доступа к разделу «Импланты».", show_alert=True)
        await state.clear()
        return
    """Завершить планирование"""
    patient_id = int(callback.data.replace("implant_done_", ""))
    await state.clear()

    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()

    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Имплантологическая карта", callback_data=f"implant_card_{patient_id}")
    builder.button(text="◀️ К пациенту", callback_data=f"patient_view_{patient_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"✅ **Планирование имплантации завершено**\n\n"
        f"👤 Пациент: {patient.full_name}\n\n"
        f"Для просмотра карты нажмите «📄 Имплантологическая карта»",
        reply_markup=builder.as_markup()
    )
    await callback.answer("✅ Готово")


# Генерация PDF
@router.callback_query(F.data.startswith("implant_card_"), flags={"tier": 1})
async def generate_implant_card(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession
):
    """Генерация PDF карты имплантации (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_IMPLANTS):
        await callback.answer("Нет доступа к разделу «Импланты».", show_alert=True)
        return
    patient_id = int(callback.data.replace("implant_card_", ""))

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    stmt = select(ImplantLog).where(
        and_(
            ImplantLog.patient_id == patient_id,
            ImplantLog.doctor_id == effective_doctor.id
        )
    ).order_by(ImplantLog.operation_date)

    result = await db_session.execute(stmt)
    implants = list(result.scalars().all())

    if not implants:
        await callback.answer("❌ Нет данных об имплантации", show_alert=True)
        return

    import asyncio
    from aiogram.types import BufferedInputFile

    try:
        from app.services.pdf_generator import generate_implant_card_pdf

        pdf_bytes = await asyncio.to_thread(
            generate_implant_card_pdf,
            user, patient, implants
        )

        pdf_file = BufferedInputFile(
            pdf_bytes,
            filename=f"implant_card_{patient.full_name.replace(' ', '_')}.pdf"
        )

        await callback.message.answer_document(
            document=pdf_file,
            caption=f"📄 Карта имплантации пациента {patient.full_name}"
        )
        await callback.answer("✅ PDF карта сгенерирована")
    except Exception as e:
        await callback.answer(f"❌ Ошибка генерации PDF: {str(e)}", show_alert=True)
