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
from app.services.notification_service import notify_patient_changed, notify_patient_created

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
    from app.utils.validators import MAX_NAME_LENGTH
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("❌ ФИО должно содержать минимум 3 символа. Попробуйте еще раз:")
        return
    if len(full_name) > MAX_NAME_LENGTH:
        await message.answer(f"❌ ФИО слишком длинное (максимум {MAX_NAME_LENGTH} символов). Попробуйте ещё раз:")
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
        from app.utils.validators import validate_phone
        if not validate_phone(message.text.strip()):
            await message.answer("❌ Некорректный номер телефона (минимум 10 цифр). Попробуйте снова или /skip:")
            return
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

    await notify_patient_created(message.bot, db_session, effective_doctor.id, patient, message.from_user.id)

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
    builder.button(text="✏️ Редактировать", callback_data=f"patient_edit_{patient.id}")
    builder.button(text="📋 История болезни", callback_data=f"patient_history_{patient.id}")
    builder.button(text="🔩 Добавить имплант", callback_data=f"implant_add_{patient.id}")
    builder.button(text="📄 Карта имплантации", callback_data=f"implant_card_{patient.id}")
    builder.adjust(1)
    
    text = "\n".join(text_parts)
    
    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())


# ── Редактирование пациента ──────────────────────────────────────────

@router.callback_query(F.data.startswith("patient_edit_"))
async def start_edit_patient(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Показать меню редактирования пациента."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на редактирование пациентов.", show_alert=True)
        return

    patient_id = int(callback.data.replace("patient_edit_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text=f"👤 ФИО: {patient.full_name}", callback_data=f"pedit_name_{patient.id}")
    builder.button(
        text=f"📞 Телефон: {patient.phone or 'не указан'}",
        callback_data=f"pedit_phone_{patient.id}",
    )
    builder.button(
        text=f"🎂 Дата рождения: {patient.birth_date.strftime('%d.%m.%Y') if patient.birth_date else 'не указана'}",
        callback_data=f"pedit_bdate_{patient.id}",
    )
    builder.button(
        text=f"📝 Заметки: {(patient.notes[:30] + '...') if patient.notes and len(patient.notes) > 30 else (patient.notes or 'нет')}",
        callback_data=f"pedit_notes_{patient.id}",
    )
    builder.button(text="← Назад", callback_data=f"patient_view_{patient.id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"✏️ **Редактирование пациента**\n\n"
        f"Выберите поле для изменения:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pedit_name_"))
async def edit_patient_name_start(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Начало редактирования ФИО."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на редактирование.", show_alert=True)
        return
    patient_id = int(callback.data.replace("pedit_name_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    await state.update_data(editing_patient_id=patient_id)
    await state.set_state(PatientStates.edit_full_name)
    await callback.message.edit_text(
        f"👤 Текущее ФИО: **{patient.full_name}**\n\n"
        "Введите новое ФИО:"
    )
    await callback.answer()


@router.message(StateFilter(PatientStates.edit_full_name))
async def process_edit_name(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка нового ФИО."""
    from app.utils.validators import MAX_NAME_LENGTH
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.answer("❌ ФИО должно содержать минимум 3 символа. Попробуйте ещё раз:")
        return
    if len(name) > MAX_NAME_LENGTH:
        await message.answer(f"❌ ФИО слишком длинное (максимум {MAX_NAME_LENGTH} символов).")
        return

    data = await state.get_data()
    patient_id = data.get("editing_patient_id")
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await message.answer("❌ Пациент не найден.")
        await state.clear()
        return

    old_name = patient.full_name
    patient.full_name = name
    await db_session.commit()
    await state.clear()
    await notify_patient_changed(
        message.bot, db_session, effective_doctor.id,
        name, "ФИО", old_name, name, message.from_user.id,
    )
    await message.answer(f"✅ ФИО изменено на **{name}**.")
    await _show_patient_info(message, patient)


@router.callback_query(F.data.startswith("pedit_phone_"))
async def edit_patient_phone_start(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Начало редактирования телефона."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на редактирование.", show_alert=True)
        return
    patient_id = int(callback.data.replace("pedit_phone_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    await state.update_data(editing_patient_id=patient_id)
    await state.set_state(PatientStates.edit_phone)
    current = patient.phone or "не указан"
    await callback.message.edit_text(
        f"📞 Текущий телефон: **{current}**\n\n"
        "Введите новый номер телефона (или /clear чтобы удалить):"
    )
    await callback.answer()


@router.message(StateFilter(PatientStates.edit_phone))
async def process_edit_phone(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка нового телефона."""
    text = (message.text or "").strip()

    data = await state.get_data()
    patient_id = data.get("editing_patient_id")
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await message.answer("❌ Пациент не найден.")
        await state.clear()
        return

    old_phone = patient.phone or "не указан"

    if text.lower() == "/clear":
        patient.phone = None
        await db_session.commit()
        await state.clear()
        await notify_patient_changed(
            message.bot, db_session, effective_doctor.id,
            patient.full_name, "Телефон", old_phone, "удалён", message.from_user.id,
        )
        await message.answer("✅ Телефон удалён.")
        await _show_patient_info(message, patient)
        return

    from app.utils.validators import validate_phone
    if not validate_phone(text):
        await message.answer("❌ Некорректный номер (минимум 10 цифр). Попробуйте ещё раз или /clear:")
        return

    patient.phone = text
    await db_session.commit()
    await state.clear()
    await notify_patient_changed(
        message.bot, db_session, effective_doctor.id,
        patient.full_name, "Телефон", old_phone, text, message.from_user.id,
    )
    await message.answer(f"✅ Телефон изменён на **{text}**.")
    await _show_patient_info(message, patient)


@router.callback_query(F.data.startswith("pedit_bdate_"))
async def edit_patient_bdate_start(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Начало редактирования даты рождения."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на редактирование.", show_alert=True)
        return
    patient_id = int(callback.data.replace("pedit_bdate_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    await state.update_data(editing_patient_id=patient_id)
    await state.set_state(PatientStates.edit_birth_date)
    current = patient.birth_date.strftime('%d.%m.%Y') if patient.birth_date else "не указана"
    await callback.message.edit_text(
        f"🎂 Текущая дата рождения: **{current}**\n\n"
        "Введите новую дату (ДД.ММ.ГГГГ, например: 15.03.1990) или /clear:"
    )
    await callback.answer()


@router.message(StateFilter(PatientStates.edit_birth_date))
async def process_edit_bdate(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка новой даты рождения."""
    text = (message.text or "").strip()

    data = await state.get_data()
    patient_id = data.get("editing_patient_id")
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await message.answer("❌ Пациент не найден.")
        await state.clear()
        return

    old_bdate = patient.birth_date.strftime('%d.%m.%Y') if patient.birth_date else "не указана"

    if text.lower() == "/clear":
        patient.birth_date = None
        await db_session.commit()
        await state.clear()
        await notify_patient_changed(
            message.bot, db_session, effective_doctor.id,
            patient.full_name, "Дата рождения", old_bdate, "удалена", message.from_user.id,
        )
        await message.answer("✅ Дата рождения удалена.")
        await _show_patient_info(message, patient)
        return

    parsed_date = None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue

    if not parsed_date:
        await message.answer("❌ Неверный формат. Введите дату как ДД.ММ.ГГГГ (например: 15.03.1990):")
        return

    if parsed_date > date.today():
        await message.answer("❌ Дата рождения не может быть в будущем.")
        return

    patient.birth_date = parsed_date
    await db_session.commit()
    await state.clear()
    await notify_patient_changed(
        message.bot, db_session, effective_doctor.id,
        patient.full_name, "Дата рождения", old_bdate, parsed_date.strftime('%d.%m.%Y'), message.from_user.id,
    )
    await message.answer(f"✅ Дата рождения изменена на **{parsed_date.strftime('%d.%m.%Y')}**.")
    await _show_patient_info(message, patient)


@router.callback_query(F.data.startswith("pedit_notes_"))
async def edit_patient_notes_start(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Начало редактирования заметок."""
    if not can_access(assistant_permissions, FEATURE_PATIENTS, "edit"):
        await callback.answer("Нет права на редактирование.", show_alert=True)
        return
    patient_id = int(callback.data.replace("pedit_notes_", ""))
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    await state.update_data(editing_patient_id=patient_id)
    await state.set_state(PatientStates.edit_notes)
    current = patient.notes or "нет"
    await callback.message.edit_text(
        f"📝 Текущие заметки:\n{current}\n\n"
        "Введите новые заметки (или /clear чтобы удалить):"
    )
    await callback.answer()


@router.message(StateFilter(PatientStates.edit_notes))
async def process_edit_notes(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Обработка новых заметок."""
    from app.utils.validators import MAX_NOTES_LENGTH
    text = (message.text or "").strip()

    data = await state.get_data()
    patient_id = data.get("editing_patient_id")
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await message.answer("❌ Пациент не найден.")
        await state.clear()
        return

    if text.lower() == "/clear":
        patient.notes = None
        await db_session.commit()
        await state.clear()
        await notify_patient_changed(
            message.bot, db_session, effective_doctor.id,
            patient.full_name, "Заметки", "были", "удалены", message.from_user.id,
        )
        await message.answer("✅ Заметки удалены.")
        await _show_patient_info(message, patient)
        return

    if len(text) > MAX_NOTES_LENGTH:
        await message.answer(f"❌ Заметки слишком длинные (максимум {MAX_NOTES_LENGTH} символов).")
        return

    patient.notes = text
    await db_session.commit()
    await state.clear()
    await notify_patient_changed(
        message.bot, db_session, effective_doctor.id,
        patient.full_name, "Заметки", "обновлены", text[:50], message.from_user.id,
    )
    await message.answer("✅ Заметки обновлены.")
    await _show_patient_info(message, patient)

