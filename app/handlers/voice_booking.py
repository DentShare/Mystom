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

from app.config import Config
from app.database.models import User, Patient, Appointment, Treatment
from app.states.voice_booking import VoiceBookingStates
from app.services.patient_service import search_patients
from app.services.notification_service import notify_new_appointment
from app.services.ai_service import (
    transcribe_voice,
    parse_image_for_booking,
    parse_booking_text,
    ParsedBooking,
)

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
        vb_service=parsed.service,
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
        # Один пациент — сразу к подтверждению
        await state.update_data(vb_patient_id=patients[0].id, vb_patient_full_name=patients[0].full_name)
        await _show_confirmation(status_msg, state)
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
        builder.button(text="❌ Отмена", callback_data="vb_cancel")
        builder.adjust(1)

        await status_msg.edit_text(
            f"🔍 По имени «{patient_name}» найдено {len(patients)} пациентов.\n"
            "Выберите нужного:",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(VoiceBookingStates.choosing_patient)
        return

    # Не найден — предлагаем создать
    builder = InlineKeyboardBuilder()
    builder.button(text=f"➕ Создать «{patient_name}»", callback_data="vb_create_patient")
    builder.button(text="❌ Отмена", callback_data="vb_cancel")
    builder.adjust(1)

    await status_msg.edit_text(
        f"❌ Пациент «{patient_name}» не найден в базе.\n\n"
        "Создать нового пациента?",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(VoiceBookingStates.choosing_patient)


# ── 4. Выбор пациента (callback) ──────────────────────────────────────

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

    # Проверяем, есть ли дата/время
    data = await state.get_data()
    if not data.get("vb_date"):
        await callback.message.edit_text("📅 Введите дату приёма (например: 15.03, завтра, понедельник):")
        await state.set_state(VoiceBookingStates.entering_date)
        return
    if not data.get("vb_time"):
        await callback.message.edit_text("⏰ Введите время приёма (например: 14:30):")
        await state.set_state(VoiceBookingStates.entering_time)
        return

    await _show_confirmation(callback.message, state)


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


@router.callback_query(F.data == "vb_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена записи."""
    await state.clear()
    await callback.message.edit_text("❌ Запись отменена.")
    await callback.answer()


# ── 5. Ввод телефона нового пациента ───────────────────────────────────

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

    # Проверяем дату/время
    if not data.get("vb_date"):
        await message.answer("📅 Введите дату приёма (например: 15.03, завтра, понедельник):")
        await state.set_state(VoiceBookingStates.entering_date)
        return
    if not data.get("vb_time"):
        await message.answer("⏰ Введите время приёма (например: 14:30):")
        await state.set_state(VoiceBookingStates.entering_time)
        return

    await _show_confirmation(message, state)


# ── 6. Ручной ввод даты ───────────────────────────────────────────────

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

    if not data.get("vb_time"):
        await message.answer("⏰ Введите время приёма (например: 14:30):")
        await state.set_state(VoiceBookingStates.entering_time)
        return

    await _show_confirmation(message, state)


# ── 7. Ручной ввод времени ─────────────────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.entering_time))
async def handle_time_input(
    message: Message,
    state: FSMContext,
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

    data = await state.get_data()
    if not data.get("vb_service"):
        await message.answer(
            "🏥 Какая услуга? Введите текстом (например: лечение кариеса, консультация, удаление) или /skip:"
        )
        await state.set_state(VoiceBookingStates.choosing_service)
        return

    await _show_confirmation(message, state)


# ── 8. Ввод услуги ────────────────────────────────────────────────────

@router.message(StateFilter(VoiceBookingStates.choosing_service))
async def handle_service_input(
    message: Message,
    state: FSMContext,
):
    """Ручной ввод услуги."""
    text = (message.text or "").strip()
    if text.lower() == "/skip":
        text = None

    await state.update_data(vb_service=text)
    await _show_confirmation(message, state)


# ── 9. Ручной ввод имени пациента (choosing_patient + manual) ──────────

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


# ── 10. Подтверждение записи ───────────────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext):
    """Показать сводку и кнопки подтверждения."""
    data = await state.get_data()

    patient_name = data.get("vb_patient_full_name") or data.get("vb_patient_name", "—")
    date_str = data.get("vb_date", "—")
    time_str = data.get("vb_time", "—")
    service = data.get("vb_service") or "Не указана"

    # Форматируем дату
    display_date = date_str
    try:
        d = date.fromisoformat(date_str)
        days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        display_date = f"{d.strftime('%d.%m.%Y')} ({days_ru[d.weekday()]})"
    except (ValueError, TypeError):
        pass

    text = (
        "📋 **Подтверждение записи**\n\n"
        f"👤 Пациент: **{patient_name}**\n"
        f"📅 Дата: **{display_date}**\n"
        f"⏰ Время: **{time_str}**\n"
        f"🏥 Услуга: **{service}**\n\n"
        "Всё верно?"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="vb_confirm")
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
    service_text = data.get("vb_service")

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
        date_time=appointment_dt,
        duration_minutes=30,
        service_description=service_text,
        status="planned",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)

    # Создаём Treatment если есть услуга
    if service_text:
        treatment = Treatment(
            patient_id=patient_id,
            doctor_id=effective_doctor.id,
            appointment_id=appointment.id,
            service_name=service_text,
        )
        db_session.add(treatment)
        await db_session.commit()

    await notify_new_appointment(callback.bot, db_session, appointment, callback.from_user.id)

    patient_name = data.get("vb_patient_full_name", "—")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    display_date = f"{d.strftime('%d.%m.%Y')} ({days_ru[d.weekday()]})"

    await callback.message.edit_text(
        f"✅ **Запись создана!**\n\n"
        f"👤 {patient_name}\n"
        f"📅 {display_date} в {time_str}\n"
        f"🏥 {service_text or 'Без услуги'}\n"
        f"🆔 Запись #{appointment.id}"
    )
    await state.clear()
    await callback.answer("✅ Записано!")


# ── 11. Редактирование из подтверждения ────────────────────────────────

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
async def cb_edit_service(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏥 Введите услугу (например: лечение кариеса, консультация):")
    await state.set_state(VoiceBookingStates.choosing_service)
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
