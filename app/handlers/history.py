from datetime import datetime
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.database.models import User, Patient, Treatment
from app.states.history import HistoryStates
from app.utils.permissions import can_access, FEATURE_HISTORY, FEATURE_FINANCE
from app.services.patient_service import get_all_patients
from app.services.service_service import (
    get_categories,
    get_services_by_category,
    ensure_default_services,
    get_service_by_id,
    CATEGORIES,
)
from app.utils.formatters import format_money, treatment_effective_price
import asyncio
from aiogram.types import BufferedInputFile

router = Router(name="history")


@router.message(F.text == "📋 История болезни", flags={'tier': 1})
async def cmd_history(
    message: Message,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Главное меню истории болезни (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_HISTORY):
        await message.answer("Нет доступа к разделу «История болезни».")
        return
    patients = await get_all_patients(db_session, effective_doctor.id)
    
    if not patients:
        await message.answer(
            "📋 **История болезни**\n\n"
            "У вас пока нет пациентов.\n"
            "Добавьте пациента через раздел «👥 Пациенты»."
        )
        return
    
    builder = InlineKeyboardBuilder()
    for patient in patients[:20]:
        builder.button(
            text=f"{patient.full_name}",
            callback_data=f"patient_history_{patient.id}"
        )
    builder.adjust(1)
    
    await message.answer(
        f"📋 **История болезни**\n\n"
        f"Выберите пациента для просмотра истории:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("patient_history_"))
async def view_patient_history(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    """Просмотр истории болезни пациента (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_HISTORY):
        await callback.answer("Нет доступа к разделу «История болезни».", show_alert=True)
        return
    await state.clear()
    patient_id = int(callback.data.replace("patient_history_", ""))
    
    stmt = select(Patient).where(
        and_(
            Patient.id == patient_id,
            Patient.doctor_id == effective_doctor.id
        )
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()
    
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return
    
    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(desc(Treatment.created_at))
    
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())
    
    # Формируем текст истории
    text_parts = []
    text_parts.append(f"📋 **История болезни**\n")
    text_parts.append(f"━━━━━━━━━━━━━━━━━━━━")
    text_parts.append(f"")
    text_parts.append(f"👤 Пациент: **{patient.full_name}**\n")
    
    if treatments:
        text_parts.append(f"📝 **Записи:** ({len(treatments)})\n")
        for i, treatment in enumerate(treatments, 1):
            date_str = treatment.created_at.strftime("%d.%m.%Y %H:%M")
            text_parts.append(f"\n**{i}. {date_str}**")
            
            if treatment.service_name:
                if effective_doctor.subscription_tier >= 2 and treatment.price is not None:
                    eff = treatment_effective_price(
                        treatment.price, treatment.discount_percent, treatment.discount_amount
                    )
                    price_str = f" — {format_money(eff)}"
                    if (treatment.discount_percent or treatment.discount_amount):
                        price_str += " (со скидкой)"
                    paid = treatment.paid_amount or 0
                    if paid > 0:
                        price_str += f", оплачено {format_money(paid)}"
                    status = treatment.payment_status or "debt"
                    if status == "full":
                        price_str += " ✅"
                    elif status == "partial":
                        price_str += " ⏳"
                    else:
                        price_str += " 💳"
                    text_parts.append(f"   🏥 Услуга: {treatment.service_name}{price_str}")
                else:
                    price_str = f" — {format_money(treatment.price)}" if treatment.price is not None and effective_doctor.subscription_tier >= 2 else ""
                    text_parts.append(f"   🏥 Услуга: {treatment.service_name}{price_str}")
            if treatment.treatment_notes:
                text_parts.append(f"   📝 {treatment.treatment_notes}")
            if treatment.tooth_number:
                text_parts.append(f"   🦷 Зуб: {treatment.tooth_number}")
    else:
        text_parts.append(f"\n📝 Записей пока нет.")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить запись", callback_data=f"history_add_{patient_id}")
    builder.button(text="🔩 Добавить имплант", callback_data=f"implant_add_{patient_id}")
    builder.button(text="📄 Имплантологическая карта", callback_data=f"implant_card_{patient_id}")
    if effective_doctor.subscription_tier >= 2:
        builder.button(text="💰 Счёт (PDF)", callback_data=f"history_invoice_{patient_id}")
        builder.button(text="💵 Внести оплату", callback_data=f"history_payment_{patient_id}")
    builder.button(text="◀️ Назад", callback_data=f"patient_view_{patient_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "\n".join(text_parts),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history_invoice_"), flags={"tier": 2})
async def generate_history_invoice(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession
):
    """Генерация PDF счёта по истории лечения (Premium, доступ по FEATURE_FINANCE)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await callback.answer("Нет доступа к финансовым функциям.", show_alert=True)
        return
    patient_id = int(callback.data.replace("history_invoice_", ""))

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(Treatment.created_at)
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())

    if not treatments:
        await callback.answer("❌ Нет записей для формирования счёта", show_alert=True)
        return

    try:
        from app.services.pdf_generator import generate_invoice_pdf

        pdf_bytes = await asyncio.to_thread(
            generate_invoice_pdf,
            effective_doctor, patient, treatments
        )
        pdf_file = BufferedInputFile(
            pdf_bytes,
            filename=f"invoice_{patient.full_name.replace(' ', '_')}.pdf"
        )
        await callback.message.answer_document(
            document=pdf_file,
            caption=f"💰 Счёт для пациента {patient.full_name}"
        )
        await callback.answer("✅ Счёт сгенерирован")
    except Exception as e:
        await callback.answer(f"❌ Ошибка генерации: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("history_add_"))
async def start_add_history_entry(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    """Начало добавления записи в историю (доступ edit по FEATURE_HISTORY)."""
    if not can_access(assistant_permissions, FEATURE_HISTORY, "edit"):
        await callback.answer("Нет права на добавление записей в историю.", show_alert=True)
        return
    patient_id = int(callback.data.replace("history_add_", ""))
    await state.update_data(history_patient_id=patient_id)

    await ensure_default_services(db_session, effective_doctor.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"history_cat_{cat_id}")
    builder.button(text="📝 Ввести вручную", callback_data="history_service_manual")
    builder.button(text="❌ Отмена", callback_data=f"patient_history_{patient_id}")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        "📝 **Добавление записи в историю**\n\n"
        "Выберите категорию услуги:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()
    await state.set_state(HistoryStates.select_service_category)


@router.callback_query(StateFilter(HistoryStates.select_service_category), F.data.startswith("history_cat_"))
async def history_select_category(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Выбор категории — показываем услуги (данные врача)."""
    category = callback.data.replace("history_cat_", "")
    data = await state.get_data()
    patient_id = data.get("history_patient_id")

    services = await get_services_by_category(db_session, effective_doctor.id, category)
    cat_name, cat_emoji = CATEGORIES.get(category, ("", ""))

    builder = InlineKeyboardBuilder()
    for svc in services:
        text = f"{svc.name} — {format_money(svc.price)}"
        if len(text) > 55:
            text = svc.name[:50] + "..."
        builder.button(text=text, callback_data=f"history_svc_{svc.id}")
    builder.button(text="← Назад", callback_data=f"history_back_{patient_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📝 {cat_emoji} {cat_name}\n\nВыберите услугу:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(HistoryStates.select_service)
    await callback.answer()


@router.callback_query(StateFilter(HistoryStates.select_service_category), F.data == "history_service_manual")
async def history_service_manual(callback: CallbackQuery, state: FSMContext):
    """Ввод услуги вручную"""
    await callback.message.edit_text(
        "📝 Введите название оказанной услуги:"
    )
    await state.set_state(HistoryStates.enter_service_manual)
    await callback.answer()




@router.callback_query(StateFilter(HistoryStates.select_service), F.data.startswith("history_back_"))
async def history_back_to_categories(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Назад к выбору категории (данные врача)."""
    patient_id = int(callback.data.replace("history_back_", ""))
    await state.update_data(history_patient_id=patient_id)
    await ensure_default_services(db_session, effective_doctor.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"history_cat_{cat_id}")
    builder.button(text="📝 Ввести вручную", callback_data="history_service_manual")
    builder.button(text="❌ Отмена", callback_data=f"patient_history_{patient_id}")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        "📝 **Добавление записи в историю**\n\nВыберите категорию услуги:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(HistoryStates.select_service_category)
    await callback.answer()


@router.callback_query(StateFilter(HistoryStates.select_service), F.data.startswith("history_svc_"))
async def history_select_service(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Выбор услуги — запрашиваем комментарий (данные врача)."""
    service_id = int(callback.data.replace("history_svc_", ""))
    service = await get_service_by_id(db_session, service_id, effective_doctor.id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    await state.update_data(
        history_service_name=service.name,
        history_service_price=service.price if effective_doctor.subscription_tier >= 2 else None,
    )
    await callback.message.edit_text(
        f"📝 Услуга: **{service.name}**\n\n"
        "Введите комментарий к оказанной услуге (или /skip для пропуска):"
    )
    await state.set_state(HistoryStates.enter_comment)
    await callback.answer()


@router.message(StateFilter(HistoryStates.enter_service_manual), F.text)
async def process_history_service_manual(
    message: Message,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка ручного ввода услуги"""
    service_name = message.text.strip()
    if len(service_name) < 2:
        await message.answer("❌ Название услуги должно содержать минимум 2 символа:")
        return

    await state.update_data(
        history_service_name=service_name,
        history_service_price=None,
    )
    await message.answer(
        f"📝 Услуга: **{service_name}**\n\n"
        "Введите комментарий к оказанной услуге (или /skip для пропуска):"
    )
    await state.set_state(HistoryStates.enter_comment)


@router.message(StateFilter(HistoryStates.enter_comment), F.text)
async def process_history_comment(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_HISTORY, "edit"):
        await message.answer("🚫 Недостаточно прав для добавления записей.")
        await state.clear()
        return
    """Обработка комментария; для Premium с ценой — запрос скидки на услугу (данные врача)."""
    comment = message.text.strip() if message.text else ""
    if message.text and message.text.strip().lower() == "/skip":
        comment = None

    data = await state.get_data()
    patient_id = data.get("history_patient_id")
    service_name = data.get("history_service_name")
    service_price = data.get("history_service_price")

    if not patient_id or not service_name:
        await message.answer("❌ Ошибка: не указан пациент или услуга")
        await state.clear()
        return

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        await message.answer("❌ Пациент не найден")
        await state.clear()
        return

    await state.update_data(history_comment=comment)

    if effective_doctor.subscription_tier >= 2 and service_price is not None:
        await message.answer(
            f"📝 Услуга: **{service_name}** — {format_money(service_price)}\n\n"
            "💸 Скидка на эту услугу: введите **процент** (например 10 или 10%) или **сумму** (например 50 000), или /skip — без скидки:"
        )
        await state.set_state(HistoryStates.enter_discount)
        return

    treatment = await _save_history_treatment(db_session, state, effective_doctor, patient_id, service_name, service_price, comment)
    patient = (await db_session.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    text = f"✅ Запись добавлена в историю!\n\n👤 Пациент: {patient.full_name}\n🏥 Услуга: {service_name}"
    if comment:
        text += f"\n📝 Комментарий: {comment}"
    if treatment:
        text += f"\n📅 {treatment.created_at.strftime('%d.%m.%Y %H:%M')}"
    await message.answer(text)
    await state.clear()


async def _save_history_treatment(
    db_session: AsyncSession,
    state: FSMContext,
    effective_doctor: User,
    patient_id: int,
    service_name: str,
    service_price: float | None,
    comment: str | None,
    discount_percent: float | None = None,
    discount_amount: float | None = None,
) -> Treatment:
    """Создать запись Treatment и сохранить в БД (от имени врача effective_doctor)."""
    treatment = Treatment(
        patient_id=patient_id,
        doctor_id=effective_doctor.id,
        service_name=service_name,
        treatment_notes=comment,
        price=service_price,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
    )
    db_session.add(treatment)
    await db_session.commit()
    await db_session.refresh(treatment)
    return treatment


@router.message(StateFilter(HistoryStates.enter_discount), F.text)
async def process_history_discount(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_HISTORY, "edit"):
        await message.answer("🚫 Недостаточно прав для добавления записей.")
        await state.clear()
        return
    """Обработка скидки на услугу (Premium, данные врача): процент, сумма или /skip"""
    text = (message.text or "").strip().lower()
    if text == "/skip" or not text:
        discount_percent = None
        discount_amount = None
    else:
        discount_percent = None
        discount_amount = None
        # Процент: "10", "10%"
        if "%" in message.text:
            try:
                num_str = message.text.replace("%", "").replace(",", ".").strip()
                discount_percent = float(num_str)
                if discount_percent < 0 or discount_percent > 100:
                    await message.answer("❌ Процент скидки от 0 до 100. Попробуйте снова:")
                    return
            except ValueError:
                await message.answer("❌ Введите процент (например 10 или 10%) или сумму, или /skip:")
                return
        else:
            try:
                num_str = message.text.replace(" ", "").replace(",", ".").strip()
                discount_amount = float(num_str)
                if discount_amount < 0:
                    await message.answer("❌ Сумма скидки не может быть отрицательной:")
                    return
            except ValueError:
                await message.answer("❌ Введите число (сумма скидки в сумах), процент (10%) или /skip:")
                return

    data = await state.get_data()
    patient_id = data.get("history_patient_id")
    service_name = data.get("history_service_name")
    service_price = data.get("history_service_price")

    if service_price is not None and discount_amount is not None and discount_amount > service_price:
        await message.answer(
            f"❌ Сумма скидки ({format_money(discount_amount)}) не может превышать цену услуги ({format_money(service_price)}):"
        )
        return
    comment = data.get("history_comment")

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        await message.answer("❌ Пациент не найден")
        await state.clear()
        return

    await _save_history_treatment(
        db_session, state, effective_doctor, patient_id, service_name, service_price, comment,
        discount_percent=discount_percent, discount_amount=discount_amount
    )
    eff = treatment_effective_price(service_price, discount_percent, discount_amount)
    msg = f"✅ Запись добавлена!\n\n👤 {patient.full_name}\n🏥 {service_name} — итого {format_money(eff)}"
    if discount_percent or discount_amount:
        msg += " (со скидкой)"
    await message.answer(msg)
    await state.clear()


# --- Внесение оплаты (Premium): скидка на всю работу + сумма и способ оплаты ---

def _treatment_debt(t) -> float:
    """Долг по позиции: итоговая цена минус уже оплачено."""
    eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
    paid = t.paid_amount or 0
    return max(0, round(eff - paid, 2))


@router.callback_query(F.data.startswith("history_payment_"), flags={"tier": 2})
async def start_payment_flow(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    """Начало внесения оплаты (Premium, доступ FEATURE_FINANCE)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE, "edit"):
        await callback.answer("Нет доступа к внесению оплаты.", show_alert=True)
        return
    patient_id = int(callback.data.replace("history_payment_", ""))
    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(Treatment.id)
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())

    # Только позиции с ценой и с долгом
    rows = []
    total_due = 0.0
    for t in treatments:
        if t.price is None:
            continue
        debt = _treatment_debt(t)
        if debt <= 0:
            continue
        eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        rows.append((t, eff, debt))
        total_due += debt

    if not rows:
        await callback.answer("❌ Нет неоплаченных позиций с указанной ценой", show_alert=True)
        return

    await state.update_data(
        history_patient_id=patient_id,
        payment_whole_discount_value=None,
    )
    await state.set_state(HistoryStates.payment_whole_discount)

    lines = [f"👤 **{patient.full_name}**\n\n💳 Неоплаченные позиции:"]
    for t, eff, debt in rows:
        lines.append(f"• {t.service_name or 'Услуга'} — {format_money(eff)}, долг {format_money(debt)}")
    lines.append(f"\n📊 **Итого к оплате:** {format_money(total_due)}")
    lines.append("\n💸 Введите **скидку на всю работу**: сумма (например 50 000) или процент (10%), или /skip — без скидки:")

    await callback.message.edit_text("\n".join(lines))
    await callback.answer()


@router.message(StateFilter(HistoryStates.payment_whole_discount), F.text)
async def process_payment_whole_discount(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_FINANCE, "edit"):
        await message.answer("🚫 Недостаточно прав для внесения оплаты.")
        await state.clear()
        return
    """Скидка на всю работу: сумма или %, или /skip (данные врача)."""
    text = (message.text or "").strip().lower()
    whole_discount = 0.0
    if text and text != "/skip":
        if "%" in message.text:
            try:
                num_str = message.text.replace("%", "").replace(",", ".").strip()
                pct = float(num_str)
                if pct < 0 or pct > 100:
                    await message.answer("❌ Процент от 0 до 100:")
                    return
                # Процент от общей суммы долга сохраняем как отрицательный процент для расчёта ниже
                await state.update_data(payment_whole_discount_percent=pct, payment_whole_discount_amount=None)
            except ValueError:
                await message.answer("❌ Введите процент (10%) или сумму, или /skip:")
                return
        else:
            try:
                num_str = message.text.replace(" ", "").replace(",", ".").strip()
                whole_discount = float(num_str)
                if whole_discount < 0:
                    await message.answer("❌ Сумма скидки не может быть отрицательной:")
                    return
                await state.update_data(payment_whole_discount_amount=whole_discount, payment_whole_discount_percent=None)
            except ValueError:
                await message.answer("❌ Введите сумму или процент (10%), или /skip:")
                return
    else:
        await state.update_data(payment_whole_discount_amount=None, payment_whole_discount_percent=None)

    data = await state.get_data()
    patient_id = data.get("history_patient_id")
    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(Treatment.id)
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())
    rows = []
    total_due = 0.0
    for t in treatments:
        if t.price is None:
            continue
        debt = _treatment_debt(t)
        if debt <= 0:
            continue
        eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        rows.append((t, eff, debt))
        total_due += debt

    whole_amount = data.get("payment_whole_discount_amount") or 0
    whole_percent = data.get("payment_whole_discount_percent")
    if whole_percent is not None:
        total_after_discount = total_due * (1 - whole_percent / 100)
    else:
        total_after_discount = max(0, total_due - whole_amount)

    await state.set_state(HistoryStates.payment_amount)
    await message.answer(
        f"📊 Итого к оплате (после скидки на всю работу): **{format_money(total_after_discount)}**\n\n"
        "Введите **внесённую сумму** (число, в сумах):"
    )


@router.message(StateFilter(HistoryStates.payment_amount), F.text)
async def process_payment_amount(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_FINANCE, "edit"):
        await message.answer("🚫 Недостаточно прав для внесения оплаты.")
        await state.clear()
        return
    """Внесённая сумма — проверка на превышение итога, затем выбор способа оплаты (данные врача)."""
    try:
        num_str = (message.text or "").replace(" ", "").replace(",", ".").strip()
        amount = float(num_str)
        if amount <= 0:
            await message.answer("❌ Введите положительную сумму:")
            return
    except ValueError:
        await message.answer("❌ Введите число (внесённая сумма в сумах):")
        return

    data = await state.get_data()
    patient_id = data.get("history_patient_id")
    whole_amount = data.get("payment_whole_discount_amount") or 0
    whole_percent = data.get("payment_whole_discount_percent")

    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(Treatment.id)
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())
    total_due = 0.0
    for t in treatments:
        if t.price is None:
            continue
        debt = _treatment_debt(t)
        if debt <= 0:
            continue
        total_due += debt

    if whole_percent is not None:
        total_after_discount = total_due * (1 - whole_percent / 100)
    else:
        total_after_discount = max(0, total_due - whole_amount)

    if amount > total_after_discount:
        await message.answer(
            f"❌ Нельзя внести больше итоговой суммы.\n\n"
            f"📊 Итого к оплате: **{format_money(total_after_discount)}**\n"
            f"Введите сумму не больше этой или выберите меньшую скидку."
        )
        return

    await state.update_data(payment_amount=amount)
    await state.set_state(HistoryStates.payment_method)

    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Наличные", callback_data="pay_method_cash")
    builder.button(text="💳 Карта", callback_data="pay_method_card")
    builder.button(text="📤 Перевод", callback_data="pay_method_transfer")
    builder.adjust(1)

    await message.answer(
        f"✅ Сумма **{format_money(amount)}** принята.\n\nВыберите способ оплаты:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(
    StateFilter(HistoryStates.payment_method),
    F.data.in_({"pay_method_cash", "pay_method_card", "pay_method_transfer"})
)
async def process_payment_method(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
    db_session: AsyncSession
):
    if not can_access(assistant_permissions, FEATURE_FINANCE, "edit"):
        await callback.answer("🚫 Недостаточно прав для внесения оплаты.", show_alert=True)
        await state.clear()
        return
    """Способ оплаты — распределяем сумму по позициям и сохраняем (данные врача)."""
    method_map = {"pay_method_cash": "cash", "pay_method_card": "card", "pay_method_transfer": "transfer"}
    payment_method = method_map.get(callback.data, "cash")

    data = await state.get_data()
    patient_id = data.get("history_patient_id")
    amount = data.get("payment_amount")
    whole_amount = data.get("payment_whole_discount_amount") or 0
    whole_percent = data.get("payment_whole_discount_percent")

    stmt = select(Patient).where(
        and_(Patient.id == patient_id, Patient.doctor_id == effective_doctor.id)
    )
    result = await db_session.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        await state.clear()
        return

    stmt = select(Treatment).where(
        and_(
            Treatment.patient_id == patient_id,
            Treatment.doctor_id == effective_doctor.id
        )
    ).order_by(Treatment.id)
    result = await db_session.execute(stmt)
    treatments = list(result.scalars().all())

    # Позиции с долгом
    rows = []
    total_due = 0.0
    for t in treatments:
        if t.price is None:
            continue
        debt = _treatment_debt(t)
        if debt <= 0:
            continue
        eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        rows.append((t, eff, debt))
        total_due += debt

    if whole_percent is not None:
        total_after_discount = total_due * (1 - whole_percent / 100)
    else:
        total_after_discount = max(0, total_due - whole_amount)

    remaining = amount
    for t, eff, debt in rows:
        pay_this = min(remaining, debt)
        if pay_this <= 0:
            continue
        new_paid = (t.paid_amount or 0) + pay_this
        t.paid_amount = round(new_paid, 2)
        t.payment_method = payment_method
        if t.paid_amount >= eff - 0.01:
            t.payment_status = "full"
        else:
            t.payment_status = "partial"
        remaining -= pay_this

    await db_session.commit()

    method_name = {"cash": "наличные", "card": "карта", "transfer": "перевод"}.get(payment_method, payment_method)
    await callback.message.edit_text(
        f"✅ Оплата внесена!\n\n"
        f"👤 {patient.full_name}\n"
        f"💵 Сумма: {format_money(amount)}\n"
        f"📋 Способ: {method_name}"
    )
    await state.clear()
    await callback.answer()

