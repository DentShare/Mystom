"""
Голосовая/фото запись на приём (только для админов).
Админ отправляет голосовое или скриншот → бот распознаёт → ищет пациента → подтверждает запись.
"""
import io
import logging
from datetime import datetime, date, timedelta

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.config import Config
from app.database.models import User, Patient, Appointment, Treatment, Service
from app.states.voice_booking import VoiceBookingStates
from app.services.patient_service import search_patients
from app.services.notification_service import notify_new_appointment
from app.services.service_service import (
    ensure_default_services,
    get_categories,
    get_services_by_category,
    CATEGORIES,
)
from app.services.ai_service import (
    transcribe_voice,
    parse_image_for_booking,
    parse_booking_text,
    ParsedBooking,
)
from app.utils.formatters import format_money

router = Router(name="voice_booking")
logger = logging.getLogger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in Config.ADMIN_IDS


# ── 1. Приём голосового сообщения ──────────────────────────────────────

@router.message(F.voice)
async def handle_voice(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Голосовое сообщение → транскрипция → парсинг → поиск пациента."""
    if not _is_admin(message.from_user.id):
        return  # не-админам голос пойдёт в fallback

    if not Config.OPENAI_API_KEY:
        await message.answer("❌ OPENAI_API_KEY не настроен. Добавьте в переменные окружения.")
        return

    status_msg = await message.answer("🎙 Распознаю голосовое сообщение...")

    try:
        # Скачиваем файл
        voice_file = await message.bot.get_file(message.voice.file_id)
        voice_data = io.BytesIO()
        await message.bot.download_file(voice_file.file_path, voice_data)
        voice_bytes = voice_data.getvalue()

        # Транскрипция
        text = await transcribe_voice(voice_bytes)
        if not text:
            await status_msg.edit_text("❌ Не удалось распознать речь. Попробуйте ещё раз.")
            return

        # Парсинг
        parsed = await parse_booking_text(text)
        await status_msg.edit_text(f"🎙 Распознано: «{text}»\n\n⏳ Обрабатываю...")

        await _process_parsed_booking(message, effective_doctor, state, db_session, parsed, status_msg)

    except Exception as e:
        logger.exception("Voice booking error: %s", e)
        await status_msg.edit_text(f"❌ Ошибка при обработке голосового: {e}")


# ── 2. Приём фото/скриншота ────────────────────────────────────────────

@router.message(F.photo)
async def handle_photo(
    message: Message,
    user: User,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Скриншот → GPT Vision → парсинг → поиск пациента."""
    if not _is_admin(message.from_user.id):
        return

    if not Config.OPENAI_API_KEY:
        await message.answer("❌ OPENAI_API_KEY не настроен.")
        return

    status_msg = await message.answer("📸 Обрабатываю изображение...")

    try:
        # Берём наибольшее фото
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        photo_data = io.BytesIO()
        await message.bot.download_file(file.file_path, photo_data)
        photo_bytes = photo_data.getvalue()

        # Распознаём текст с изображения
        text = await parse_image_for_booking(photo_bytes)
        if not text:
            await status_msg.edit_text("❌ Не удалось распознать данные с изображения.")
            return

        # Парсинг
        parsed = await parse_booking_text(text)
        await status_msg.edit_text(f"📸 Распознано: «{text}»\n\n⏳ Обрабатываю...")

        await _process_parsed_booking(message, effective_doctor, state, db_session, parsed, status_msg)

    except Exception as e:
        logger.exception("Photo booking error: %s", e)
        await status_msg.edit_text(f"❌ Ошибка при обработке изображения: {e}")


# ── 3. Общая логика после парсинга ─────────────────────────────────────

async def _process_parsed_booking(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
    parsed: ParsedBooking,
    status_msg: Message,
):
    """Обработка результата парсинга: поиск пациента, проверка полей."""
    # Сохраняем данные в FSM
    await state.update_data(
        vb_patient_name=parsed.patient_name,
        vb_date=parsed.date_str,
        vb_time=parsed.time_str,
        vb_service_text=parsed.service,  # текст из распознавания (для поиска)
        vb_raw_text=parsed.raw_text,
    )

    # Проверяем обязательные поля
    missing = []
    if not parsed.patient_name:
        missing.append("имя пациента")
    if not parsed.date_str:
        missing.append("дата")
    if not parsed.time_str:
        missing.append("время")

    if missing:
        # Показываем что распознали + просим уточнить
        text = _format_recognized(parsed)
        text += f"\n\n⚠️ Не удалось определить: {', '.join(missing)}"

        if not parsed.date_str:
            text += "\n\n📅 Введите дату (например: 15.03 или завтра):"
            await status_msg.edit_text(text)
            await state.set_state(VoiceBookingStates.entering_date)
            return
        if not parsed.time_str:
            text += "\n\n⏰ Введите время (например: 14:30):"
            await status_msg.edit_text(text)
            await state.set_state(VoiceBookingStates.entering_time)
            return
        if not parsed.patient_name:
            text += "\n\n👤 Введите ФИО пациента:"
            await status_msg.edit_text(text)
            await state.set_state(VoiceBookingStates.choosing_patient)
            await state.update_data(vb_manual_name_input=True)
            return

    # Всё распознано — ищем пациента
    await _search_patient_and_continue(message, effective_doctor, state, db_session, status_msg)


async def _search_patient_and_continue(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
    status_msg: Message,
):
    """Поиск пациента в БД и продолжение."""
    data = await state.get_data()
    patient_name = data.get("vb_patient_name", "")

    patients = await search_patients(db_session, effective_doctor.id, patient_name)

    if len(patients) == 1:
        # Один пациент — продолжаем
        await state.update_data(vb_patient_id=patients[0].id, vb_patient_full_name=patients[0].full_name)
        await _check_remaining_fields(status_msg, effective_doctor, state, db_session)
        return

    if len(patients) > 1:
        # Несколько — предлагаем выбрать
        builder = InlineKeyboardBuilder()
        for p in patients[:10]:
            phone_str = f" — {p.phone}" if p.phone else ""
            btn_text = f"{p.full_name}{phone_str}"
            if len(btn_text) > 60:
                btn_text = p.full_name[:57] + "..."
            builder.button(text=btn_text, callback_data=f"vb_patient_{p.id}")
        builder.button(text="➕ Создать нового", callback_data="vb_create_patient")
        builder.button(text="✏️ Изменить имя", callback_data="vb_rename_patient")
        builder.button(text="❌ Отмена", callback_data="vb_cancel")
        builder.adjust(1)

        await status_msg.edit_text(
            f"🔍 По имени «{patient_name}» найдено {len(patients)} пациентов.\n"
            "Выберите нужного:",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(VoiceBookingStates.choosing_patient)
        return

    # Не найден — предлагаем создать или изменить имя
    builder = InlineKeyboardBuilder()
    builder.button(text=f"➕ Создать «{patient_name}»", callback_data="vb_create_patient")
    builder.button(text="✏️ Изменить имя", callback_data="vb_rename_patient")
    builder.button(text="❌ Отмена", callback_data="vb_cancel")
    builder.adjust(1)

    await status_msg.edit_text(
        f"❌ Пациент «{patient_name}» не найден в базе.\n\n"
        "Создать нового пациента?",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(VoiceBookingStates.choosing_patient)


async def _check_remaining_fields(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Проверить что все поля заполнены, иначе запросить недостающие."""
    data = await state.get_data()

    if not data.get("vb_date"):
        try:
            await message.edit_text("📅 Введите дату приёма (например: 15.03, завтра, понедельник):")
        except Exception:
            await message.answer("📅 Введите дату приёма (например: 15.03, завтра, понедельник):")
        await state.set_state(VoiceBookingStates.entering_date)
        return

    if not data.get("vb_time"):
        try:
            await message.edit_text("⏰ Введите время приёма (например: 14:30):")
        except Exception:
            await message.answer("⏰ Введите время приёма (например: 14:30):")
        await state.set_state(VoiceBookingStates.entering_time)
        return

    # Услуга: если ещё не выбрана из прайса — матчим
    if not data.get("vb_service_id"):
        await _match_service_and_continue(message, effective_doctor, state, db_session)
        return

    await _show_confirmation(message, state)


# ── 4. Поиск услуги в прайсе врача ────────────────────────────────────

async def _search_services_by_text(
    db_session: AsyncSession,
    doctor_id: int,
    query: str,
) -> list[Service]:
    """Поиск услуг врача по подстроке в названии."""
    pattern = f"%{query}%"
    stmt = (
        select(Service)
        .where(
            and_(
                Service.doctor_id == doctor_id,
                Service.name.ilike(pattern),
            )
        )
        .order_by(Service.category, Service.sort_order)
    )
    result = await db_session.execute(stmt)
    return list(result.scalars().all())


async def _match_service_and_continue(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Сопоставить распознанную услугу с прайсом врача."""
    data = await state.get_data()
    service_text = data.get("vb_service_text")  # из распознавания

    await ensure_default_services(db_session, effective_doctor.id)

    if service_text:
        # Ищем по подстроке
        matches = await _search_services_by_text(db_session, effective_doctor.id, service_text)

        if len(matches) == 1:
            # Точное совпадение — автовыбор
            svc = matches[0]
            await state.update_data(
                vb_service_id=svc.id,
                vb_service=svc.name,
                vb_service_price=svc.price,
                vb_service_duration=svc.duration_minutes,
            )
            await _show_confirmation(message, state)
            return

        if len(matches) > 1:
            # Несколько — показываем кнопки
            builder = InlineKeyboardBuilder()
            for svc in matches[:15]:
                text = f"{svc.name} — {format_money(svc.price)}"
                if len(text) > 60:
                    text = svc.name[:50] + "..."
                builder.button(text=text, callback_data=f"vb_svc_{svc.id}")
            builder.button(text="📝 Ввести вручную", callback_data="vb_svc_manual")
            builder.button(text="❌ Отмена", callback_data="vb_cancel")
            builder.adjust(1)

            try:
                await message.edit_text(
                    f"🔍 По запросу «{service_text}» найдено {len(matches)} услуг.\n"
                    "Выберите нужную:",
                    reply_markup=builder.as_markup(),
                )
            except Exception:
                await message.answer(
                    f"🔍 По запросу «{service_text}» найдено {len(matches)} услуг.\n"
                    "Выберите нужную:",
                    reply_markup=builder.as_markup(),
                )
            await state.set_state(VoiceBookingStates.choosing_service)
            return

    # Не найдено или не указано — показываем категории + все услуги
    await _show_service_picker(message, effective_doctor, state, db_session, service_text)


async def _show_service_picker(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
    hint: str | None = None,
):
    """Показать категории услуг для выбора."""
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"vb_cat_{cat_id}")
    builder.button(text="📝 Ввести вручную", callback_data="vb_svc_manual")
    builder.button(text="⏩ Без услуги", callback_data="vb_svc_skip")
    builder.button(text="❌ Отмена", callback_data="vb_cancel")
    builder.adjust(2, 2, 2, 1, 1, 1)

    hint_line = f"\n(распознано: «{hint}» — не найдено в прайсе)" if hint else ""
    text = f"📋 Выберите категорию услуги:{hint_line}"

    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())
    await state.set_state(VoiceBookingStates.choosing_service)


# ── 5. Выбор пациента (callback) ──────────────────────────────────────

@router.callback_query(F.data.startswith("vb_patient_"))
async def cb_select_patient(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Пациент выбран из списка."""
    patient_id = int(callback.data.replace("vb_patient_", ""))
    from app.services.patient_service import get_patient_by_id
    patient = await get_patient_by_id(db_session, patient_id, effective_doctor.id)
    if not patient:
        await callback.answer("❌ Пациент не найден", show_alert=True)
        return

    await state.update_data(vb_patient_id=patient.id, vb_patient_full_name=patient.full_name)
    await callback.answer()

    await _check_remaining_fields(callback.message, effective_doctor, state, db_session)


@router.callback_query(F.data == "vb_create_patient")
async def cb_create_patient(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Создание нового пациента — спрашиваем телефон."""
    data = await state.get_data()
    name = data.get("vb_patient_name", "Неизвестный")

    await callback.message.edit_text(
        f"➕ Создание пациента: **{name}**\n\n"
        "📞 Введите номер телефона для связи (или /skip):"
    )
    await state.set_state(VoiceBookingStates.entering_patient_phone)
    await callback.answer()


@router.callback_query(F.data == "vb_rename_patient")
async def cb_rename_patient(callback: CallbackQuery, state: FSMContext):
    """Изменить имя пациента (если распознано неправильно)."""
    await callback.message.edit_text(
        "✏️ Введите правильное ФИО пациента:"
    )
    await state.update_data(vb_manual_name_input=True)
    await state.set_state(VoiceBookingStates.choosing_patient)
    await callback.answer()


@router.callback_query(F.data == "vb_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена записи."""
    await state.clear()
    await callback.message.edit_text("❌ Запись отменена.")
    await callback.answer()


# ── 6. Выбор услуги (callbacks) ────────────────────────────────────────

@router.callback_query(F.data.startswith("vb_svc_"))
async def cb_select_service(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Услуга выбрана из прайса."""
    data_str = callback.data

    if data_str == "vb_svc_manual":
        await callback.message.edit_text("📝 Введите название услуги:")
        await state.set_state(VoiceBookingStates.choosing_service)
        await state.update_data(vb_manual_service_input=True)
        await callback.answer()
        return

    if data_str == "vb_svc_skip":
        await state.update_data(vb_service_id=None, vb_service=None, vb_service_price=None, vb_service_duration=30)
        await callback.answer()
        await _show_confirmation(callback.message, state)
        return

    # vb_svc_{id}
    service_id = int(data_str.replace("vb_svc_", ""))
    stmt = select(Service).where(and_(Service.id == service_id, Service.doctor_id == effective_doctor.id))
    result = await db_session.execute(stmt)
    svc = result.scalar_one_or_none()

    if not svc:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    await state.update_data(
        vb_service_id=svc.id,
        vb_service=svc.name,
        vb_service_price=svc.price,
        vb_service_duration=svc.duration_minutes,
    )
    await callback.answer()
    await _show_confirmation(callback.message, state)


@router.callback_query(F.data.startswith("vb_cat_"))
async def cb_select_category(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Выбрана категория — показываем услуги."""
    category = callback.data.replace("vb_cat_", "")
    services = await get_services_by_category(db_session, effective_doctor.id, category)
    cat_name, cat_emoji = CATEGORIES.get(category, ("", ""))

    builder = InlineKeyboardBuilder()
    for svc in services:
        text = f"{svc.name} — {format_money(svc.price)}"
        if len(text) > 60:
            text = svc.name[:50] + "..."
        builder.button(text=text, callback_data=f"vb_svc_{svc.id}")
    builder.button(text="← Назад к категориям", callback_data="vb_cat_back")
    builder.button(text="📝 Ввести вручную", callback_data="vb_svc_manual")
    builder.adjust(1)

    await callback.message.edit_text(
        f"{cat_emoji} **{cat_name}**\n\nВыберите услугу:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "vb_cat_back")
async def cb_category_back(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Назад к списку категорий."""
    await _show_service_picker(callback.message, effective_doctor, state, db_session)
    await callback.answer()


# ── 7. Ввод телефона нового пациента ───────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.entering_patient_phone))
async def handle_patient_phone(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Телефон нового пациента → создаём → продолжаем."""
    phone = None
    text = (message.text or "").strip()

    if text.lower() != "/skip" and text:
        from app.utils.validators import validate_phone
        if not validate_phone(text):
            await message.answer("❌ Некорректный номер. Попробуйте ещё раз или /skip:")
            return
        phone = text

    data = await state.get_data()
    full_name = data.get("vb_patient_name", "Неизвестный")

    patient = Patient(
        doctor_id=effective_doctor.id,
        full_name=full_name,
        phone=phone,
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)

    await state.update_data(vb_patient_id=patient.id, vb_patient_full_name=patient.full_name)
    await message.answer(f"✅ Пациент **{patient.full_name}** создан (ID: {patient.id}).")

    await _check_remaining_fields(message, effective_doctor, state, db_session)


# ── 8. Ручной ввод даты ───────────────────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.entering_date))
async def handle_date_input(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Ручной ввод даты."""
    text = (message.text or "").strip().lower()
    today = date.today()
    parsed_date = None

    if text in ("сегодня", "today"):
        parsed_date = today
    elif text in ("завтра", "tomorrow"):
        parsed_date = today + timedelta(days=1)
    elif text in ("послезавтра",):
        parsed_date = today + timedelta(days=2)
    else:
        # Попробуем ДД.ММ или ДД.ММ.ГГГГ
        for fmt in ("%d.%m", "%d.%m.%Y", "%d/%m", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                if fmt in ("%d.%m", "%d/%m"):
                    dt = dt.replace(year=today.year)
                    if dt.date() < today:
                        dt = dt.replace(year=today.year + 1)
                parsed_date = dt.date()
                break
            except ValueError:
                continue

        if not parsed_date:
            # Пробуем через GPT (дни недели и т.д.)
            try:
                from app.services.ai_service import parse_booking_text
                result = await parse_booking_text(f"запись на {text}")
                if result.date_str:
                    parsed_date = date.fromisoformat(result.date_str)
            except Exception:
                pass

    if not parsed_date:
        await message.answer("❌ Не удалось определить дату. Введите в формате ДД.ММ (например: 15.03):")
        return

    await state.update_data(vb_date=parsed_date.isoformat())

    data = await state.get_data()

    # Если ещё нет пациента (ввод имени вручную не завершён)
    if not data.get("vb_patient_id") and not data.get("vb_patient_name"):
        await message.answer("👤 Введите ФИО пациента:")
        await state.set_state(VoiceBookingStates.choosing_patient)
        await state.update_data(vb_manual_name_input=True)
        return

    # Если есть имя но нет пациента в базе — ищем
    if not data.get("vb_patient_id") and data.get("vb_patient_name"):
        status_msg = await message.answer("🔍 Ищу пациента...")
        await _search_patient_and_continue(message, effective_doctor, state, db_session, status_msg)
        return

    await _check_remaining_fields(message, effective_doctor, state, db_session)


# ── 9. Ручной ввод времени ─────────────────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.entering_time))
async def handle_time_input(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Ручной ввод времени."""
    text = (message.text or "").strip()
    parsed_time = None

    for fmt in ("%H:%M", "%H.%M", "%H %M"):
        try:
            dt = datetime.strptime(text, fmt)
            parsed_time = dt.strftime("%H:%M")
            break
        except ValueError:
            continue

    # Попробуем просто число как час
    if not parsed_time:
        try:
            hour = int(text)
            if 0 <= hour <= 23:
                parsed_time = f"{hour:02d}:00"
        except ValueError:
            pass

    if not parsed_time:
        await message.answer("❌ Не удалось определить время. Введите в формате ЧЧ:ММ (например: 14:30):")
        return

    await state.update_data(vb_time=parsed_time)
    await _check_remaining_fields(message, effective_doctor, state, db_session)


# ── 10. Ручной ввод услуги (текстом) ──────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.choosing_service))
async def handle_service_input(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Ручной ввод услуги — сначала ищем в прайсе, потом сохраняем как текст."""
    data = await state.get_data()
    if not data.get("vb_manual_service_input"):
        return  # Ожидаем callback

    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Введите название услуги:")
        return

    # Ищем в прайсе по введённому тексту
    matches = await _search_services_by_text(db_session, effective_doctor.id, text)

    if len(matches) == 1:
        svc = matches[0]
        await state.update_data(
            vb_service_id=svc.id,
            vb_service=svc.name,
            vb_service_price=svc.price,
            vb_service_duration=svc.duration_minutes,
            vb_manual_service_input=False,
        )
        await _show_confirmation(message, state)
        return

    if len(matches) > 1:
        builder = InlineKeyboardBuilder()
        for svc in matches[:15]:
            btn = f"{svc.name} — {format_money(svc.price)}"
            if len(btn) > 60:
                btn = svc.name[:50] + "..."
            builder.button(text=btn, callback_data=f"vb_svc_{svc.id}")
        builder.button(text=f"📝 Сохранить как «{text[:30]}»", callback_data="vb_svc_custom")
        builder.adjust(1)

        await state.update_data(vb_custom_service_text=text)
        await message.answer(
            f"🔍 По запросу «{text}» найдено {len(matches)} услуг.\n"
            "Выберите или сохраните введённый текст:",
            reply_markup=builder.as_markup(),
        )
        return

    # Не найдено — сохраняем как текст
    await state.update_data(
        vb_service_id=None,
        vb_service=text,
        vb_service_price=None,
        vb_service_duration=30,
        vb_manual_service_input=False,
    )
    await _show_confirmation(message, state)


@router.callback_query(F.data == "vb_svc_custom")
async def cb_save_custom_service(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Сохранить услугу как произвольный текст."""
    data = await state.get_data()
    text = data.get("vb_custom_service_text", "")
    await state.update_data(
        vb_service_id=None,
        vb_service=text,
        vb_service_price=None,
        vb_service_duration=30,
        vb_manual_service_input=False,
    )
    await callback.answer()
    await _show_confirmation(callback.message, state)


# ── 11. Ручной ввод имени пациента (choosing_patient + manual) ─────────

@router.message(StateFilter(VoiceBookingStates.choosing_patient))
async def handle_manual_patient_name(
    message: Message,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Ручной ввод имени пациента (если не распознано из голоса)."""
    data = await state.get_data()
    if not data.get("vb_manual_name_input"):
        return  # Ожидаем callback, а не текст

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("❌ Введите ФИО пациента (минимум 2 символа):")
        return

    await state.update_data(vb_patient_name=name, vb_manual_name_input=False)

    status_msg = await message.answer("🔍 Ищу пациента...")
    await _search_patient_and_continue(message, effective_doctor, state, db_session, status_msg)


# ── 12. Подтверждение записи ──────────────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext):
    """Показать сводку и кнопки подтверждения."""
    data = await state.get_data()

    patient_name = data.get("vb_patient_full_name") or data.get("vb_patient_name", "—")
    date_str = data.get("vb_date", "—")
    time_str = data.get("vb_time", "—")
    service_name = data.get("vb_service") or "Не указана"
    service_price = data.get("vb_service_price")

    # Форматируем дату
    display_date = date_str
    try:
        d = date.fromisoformat(date_str)
        days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        display_date = f"{d.strftime('%d.%m.%Y')} ({days_ru[d.weekday()]})"
    except (ValueError, TypeError):
        pass

    service_line = f"**{service_name}**"
    if service_price:
        service_line += f" — {format_money(service_price)}"

    text = (
        "📋 **Подтверждение записи**\n\n"
        f"👤 Пациент: **{patient_name}**\n"
        f"📅 Дата: **{display_date}**\n"
        f"⏰ Время: **{time_str}**\n"
        f"🏥 Услуга: {service_line}\n\n"
        "Всё верно?"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="vb_confirm")
    builder.button(text="✏️ Изменить пациента", callback_data="vb_edit_patient")
    builder.button(text="✏️ Изменить дату", callback_data="vb_edit_date")
    builder.button(text="✏️ Изменить время", callback_data="vb_edit_time")
    builder.button(text="✏️ Изменить услугу", callback_data="vb_edit_service")
    builder.button(text="❌ Отмена", callback_data="vb_cancel")
    builder.adjust(1)

    await state.set_state(VoiceBookingStates.confirming)

    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(StateFilter(VoiceBookingStates.confirming), F.data == "vb_confirm")
async def cb_confirm_booking(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Подтверждение — создаём запись в БД."""
    data = await state.get_data()
    patient_id = data.get("vb_patient_id")
    date_str = data.get("vb_date")
    time_str = data.get("vb_time")
    service_name = data.get("vb_service")
    service_id = data.get("vb_service_id")
    service_price = data.get("vb_service_price")
    duration = data.get("vb_service_duration") or 30

    if not patient_id or not date_str or not time_str:
        await callback.answer("❌ Недостаточно данных", show_alert=True)
        return

    try:
        d = date.fromisoformat(date_str)
        hour, minute = map(int, time_str.split(":"))
        appointment_dt = datetime(d.year, d.month, d.day, hour, minute)
    except (ValueError, TypeError):
        await callback.answer("❌ Ошибка формата даты/времени", show_alert=True)
        return

    appointment = Appointment(
        doctor_id=effective_doctor.id,
        patient_id=patient_id,
        service_id=service_id,
        date_time=appointment_dt,
        duration_minutes=duration,
        service_description=service_name,
        status="planned",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)

    # Создаём Treatment
    if service_name or service_id:
        treatment = Treatment(
            patient_id=patient_id,
            doctor_id=effective_doctor.id,
            appointment_id=appointment.id,
            service_name=service_name,
            price=service_price,
        )
        db_session.add(treatment)
        await db_session.commit()

    await notify_new_appointment(callback.bot, db_session, appointment, callback.from_user.id)

    patient_name = data.get("vb_patient_full_name", "—")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    display_date = f"{d.strftime('%d.%m.%Y')} ({days_ru[d.weekday()]})"

    price_str = f" — {format_money(service_price)}" if service_price else ""

    await callback.message.edit_text(
        f"✅ **Запись создана!**\n\n"
        f"👤 {patient_name}\n"
        f"📅 {display_date} в {time_str}\n"
        f"🏥 {service_name or 'Без услуги'}{price_str}\n"
        f"🆔 Запись #{appointment.id}"
    )
    await state.clear()
    await callback.answer("✅ Записано!")


# ── 13. Редактирование из подтверждения ────────────────────────────────

@router.callback_query(StateFilter(VoiceBookingStates.confirming), F.data == "vb_edit_patient")
async def cb_edit_patient(callback: CallbackQuery, state: FSMContext):
    """Изменить пациента — ввод нового имени для поиска."""
    await callback.message.edit_text(
        "👤 Введите ФИО пациента для поиска (или новое имя):"
    )
    await state.update_data(vb_manual_name_input=True, vb_patient_id=None, vb_patient_full_name=None)
    await state.set_state(VoiceBookingStates.choosing_patient)
    await callback.answer()


@router.callback_query(StateFilter(VoiceBookingStates.confirming), F.data == "vb_edit_date")
async def cb_edit_date(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📅 Введите новую дату (например: 15.03, завтра, понедельник):")
    await state.set_state(VoiceBookingStates.entering_date)
    await callback.answer()


@router.callback_query(StateFilter(VoiceBookingStates.confirming), F.data == "vb_edit_time")
async def cb_edit_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⏰ Введите новое время (например: 14:30):")
    await state.set_state(VoiceBookingStates.entering_time)
    await callback.answer()


@router.callback_query(StateFilter(VoiceBookingStates.confirming), F.data == "vb_edit_service")
async def cb_edit_service(
    callback: CallbackQuery,
    effective_doctor: User,
    state: FSMContext,
    db_session: AsyncSession,
):
    """Изменить услугу — сбрасываем и показываем категории."""
    await state.update_data(vb_service_id=None, vb_service=None, vb_service_price=None)
    await _show_service_picker(callback.message, effective_doctor, state, db_session)
    await callback.answer()


# ── Вспомогательные ────────────────────────────────────────────────────

def _format_recognized(parsed: ParsedBooking) -> str:
    """Форматирование распознанных данных."""
    lines = ["🎙 Распознано из сообщения:\n"]
    if parsed.patient_name:
        lines.append(f"👤 Пациент: {parsed.patient_name}")
    if parsed.date_str:
        try:
            d = date.fromisoformat(parsed.date_str)
            lines.append(f"📅 Дата: {d.strftime('%d.%m.%Y')}")
        except ValueError:
            lines.append(f"📅 Дата: {parsed.date_str}")
    if parsed.time_str:
        lines.append(f"⏰ Время: {parsed.time_str}")
    if parsed.service:
        lines.append(f"🏥 Услуга: {parsed.service}")
    return "\n".join(lines)
