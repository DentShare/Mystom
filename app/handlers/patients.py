from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Patient
from app.states.patient import PatientStates
from app.services.patient_service import search_patients, get_patient_by_id, get_all_patients
from app.keyboards.main import get_cancel_keyboard
from app.states.appointment import AppointmentStates
from app.utils.permissions import can_access, FEATURE_PATIENTS

router = Router(name="patients")


@router.message(F.text == "👥 Пациенты", flags={'tier': 1})
async def cmd_patients(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Главное меню пациентов (доступ по правам ассистента и тарифу врача)."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS):
        await message.answer("Нет доступа к разделу «Пациенты».")
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить пациента", callback_data="patient_add")
    builder.button(text="🔍 Поиск пациента", callback_data="patient_search")
    builder.button(text="📋 Список пациентов", callback_data="patient_list")
    builder.adjust(1)
    
    await message.answer(
        "👥 **Управление пациентами**\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "patient_add")
async def start_add_patient(
    callback: CallbackQuery,
    assistant_permissions: dict,
    state: FSMContext,
):
    """Начало добавления пациента"""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на добавление пациентов.", show_alert=True)
        return
    await callback.message.edit_text(
        "➕ **Добавление нового пациента**\n\n"
        "Введите ФИО пациента:",
        reply_markup=None
    )
    await callback.answer()
    await state.set_state(PatientStates.enter_full_name)


@router.message(StateFilter(PatientStates.enter_full_name))
async def process_patient_full_name(message: Message, state: FSMContext):
    """Обработка ввода ФИО"""
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("❌ ФИО должно содержать минимум 3 символа. Попробуйте еще раз:")
        return
    
    await state.update_data(full_name=full_name)
    await message.answer(
        "✅ ФИО сохранено!\n\n"
        "Введите телефон пациента (или /skip):"
    )
    await state.set_state(PatientStates.enter_phone)


@router.message(StateFilter(PatientStates.enter_phone))
async def process_patient_phone(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка ввода телефона (пациент создаётся у врача effective_doctor)."""
    phone = None
    if message.text and message.text.strip().lower() != "/skip":
        phone = message.text.strip()
    
    data = await state.get_data()
    full_name = data.get("full_name")
    
    patient = Patient(
        doctor_id=effective_doctor.id,
        full_name=full_name,
        phone=phone
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)
    
    if data.get("creating_for_appointment"):
        from app.handlers.calendar import _continue_appointment_creation
        await state.update_data(patient_id=patient.id, creating_for_appointment=False)
        await message.answer(f"✅ Пациент **{patient.full_name}** добавлен. Выберите услугу:")
        await _continue_appointment_creation(message, effective_doctor, state, db_session)
        return
    
    await message.answer(
        f"✅ Пациент добавлен!\n\n"
        f"👤 **{patient.full_name}**\n"
        f"📞 {patient.phone or 'Не указан'}\n"
        f"🆔 ID: {patient.id}"
    )
    await state.clear()


@router.callback_query(F.data == "patient_search")
async def start_search_patient(
    callback: CallbackQuery,
    assistant_permissions: dict,
    state: FSMContext,
):
    """Начало поиска пациента"""
    if not can_access(assistant_permissions, FEATURE_PATIENTS):
        await callback.answer("Нет доступа к разделу «Пациенты».", show_alert=True)
        return
    await callback.message.edit_text(
        "🔍 **Поиск пациента**\n\n"
        "Введите ФИО или телефон для поиска:",
        reply_markup=None
    )
    await callback.answer()
    await state.set_state(PatientStates.search_patient)


@router.message(StateFilter(PatientStates.search_patient))
async def process_patient_search(
    message: Message,
    effective_doctor: User,
    db_session: AsyncSession,
    state: FSMContext,
):
    """Обработка поиска пациента (по данным врача)."""
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("❌ Запрос должен содержать минимум 2 символа. Попробуйте еще раз:")
        return
    
    patients = await search_patients(db_session, effective_doctor.id, query)
    
    if not patients:
        await message.answer(
            f"❌ Пациенты не найдены по запросу: {query}\n\n"
            "Попробуйте другой запрос или создайте нового пациента."
        )
        return
    
    # Показываем результаты
    if len(patients) == 1:
        # Один результат - показываем сразу
        patient = patients[0]
        await _show_patient_info(message, patient)
    else:
        # Несколько результатов - показываем список
        builder = InlineKeyboardBuilder()
        for patient in patients[:10]:  # Ограничиваем 10 результатами
            builder.button(
                text=f"{patient.full_name} ({patient.phone or 'нет телефона'})",
                callback_data=f"patient_view_{patient.id}"
            )
        builder.adjust(1)
        
        await message.answer(
            f"🔍 Найдено пациентов: {len(patients)}\n\n"
            "Выберите пациента:",
            reply_markup=builder.as_markup()
        )
    
    await state.clear()


@router.callback_query(F.data.startswith("patient_view_"))
async def view_patient(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Просмотр информации о пациенте (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS):
        await callback.answer("Нет доступа к разделу «Пациенты».", show_alert=True)
        return
    patient_id = int(callback.data.replace("patient_view_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return
    
    await _show_patient_info(callback.message, patient, edit=True)
    await callback.answer()


@router.callback_query(F.data == "patient_list")
async def list_patients(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Список всех пациентов (по данным врача, доступ по правам)."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS):
        await callback.answer("Нет доступа к разделу «Пациенты».", show_alert=True)
        return
    patients = await get_all_patients(db_session, effective_doctor.id)
    
    if not patients:
        await callback.message.edit_text("📋 Список пациентов пуст.")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for patient in patients[:20]:  # Ограничиваем 20 результатами
        builder.button(
            text=f"{patient.full_name}",
            callback_data=f"patient_view_{patient.id}"
        )
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"📋 **Список пациентов** ({len(patients)}):\n\n"
        "Выберите пациента для просмотра:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


async def _show_patient_info(message: Message, patient: Patient, edit: bool = False):
    """Показать информацию о пациенте"""
    text_parts = []
    text_parts.append(f"👤 **Информация о пациенте**\n")
    text_parts.append(f"━━━━━━━━━━━━━━━━━━━━")
    text_parts.append(f"")
    text_parts.append(f"🆔 ID: {patient.id}")
    text_parts.append(f"👤 ФИО: {patient.full_name}")
    if patient.phone:
        text_parts.append(f"📞 Телефон: {patient.phone}")
    if patient.birth_date:
        text_parts.append(f"🎂 Дата рождения: {patient.birth_date.strftime('%d.%m.%Y')}")
    if patient.notes:
        text_parts.append(f"📝 Заметки: {patient.notes}")
    text_parts.append(f"")
    text_parts.append(f"📅 Создан: {patient.created_at.strftime('%d.%m.%Y %H:%M')}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 История болезни", callback_data=f"patient_history_{patient.id}")
    builder.button(text="🔩 Добавить имплант", callback_data=f"implant_add_{patient.id}")
    builder.button(text="📄 Карта имплантации", callback_data=f"implant_card_{patient.id}")
    builder.adjust(1)
    
    text = "\n".join(text_parts)
    
    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())

