from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, Location
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.keyboards.main import get_main_menu_keyboard, get_settings_keyboard
from app.services.user_service import delete_user_from_db
from app.states.settings import SettingsStates
from app.services.timezone import get_common_timezones
from app.services.reminder_service import get_reminder_minutes

router = Router(name="settings")


def _get_settings_text(user: User) -> str:
    """Текст настроек"""
    tier_names = {0: "Basic", 1: "Standard", 2: "Premium"}
    tier_name = tier_names.get(user.subscription_tier, "Basic")
    return (
        f"⚙️ **Настройки**\n\n"
        f"👤 ФИО: {user.full_name or 'Не указано'}\n"
        f"🏥 Специализация: {user.specialization or 'Не указано'}\n"
        f"📞 Телефон: {user.phone or 'Не указан'}\n"
        f"📍 Адрес: {user.address or 'Не указан'}\n"
        f"🗺 Геолокация: {'Указана' if user.location_lat else 'Не указана'}\n"
        f"📷 Фото: {'Есть' if user.photo_url else 'Нет'}\n"
        f"🌍 Часовой пояс: {user.timezone or 'Не указан'}\n"
        f"⏰ Напоминание: за {get_reminder_minutes(user)} мин до записи\n"
        f"⭐ Уровень подписки: {tier_name}\n\n"
        f"Выберите, что изменить:"
    )


def _get_settings_inline_keyboard(user: User) -> InlineKeyboardBuilder:
    """Инлайн-клавиатура редактирования"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ ФИО", callback_data="edit_full_name")
    builder.button(text="✏️ Специализация", callback_data="edit_specialization")
    builder.button(text="✏️ Телефон", callback_data="edit_phone")
    builder.button(text="✏️ Адрес", callback_data="edit_address")
    builder.button(text="📍 Геолокация", callback_data="edit_location")
    builder.button(text="📷 Фото", callback_data="edit_photo")
    builder.button(text="🌍 Часовой пояс", callback_data="edit_timezone")
    if user.subscription_tier >= 1:
        builder.button(text="⏰ Напоминание до записи", callback_data="edit_reminder")
    builder.button(text="🗑 Удалить мой аккаунт", callback_data="settings_delete_account")
    builder.button(text="⬅️ Назад в меню", callback_data="settings_back")
    builder.adjust(2)
    return builder


@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message, user: User, state: FSMContext):
    """Настройки профиля"""
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer(
        _get_settings_text(user),
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "edit_full_name")
async def edit_full_name_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования ФИО"""
    await state.set_state(SettingsStates.enter_full_name)
    await callback.message.edit_text("✏️ Введите новое ФИО (минимум 3 символа):")
    await callback.answer()


@router.callback_query(F.data == "edit_specialization")
async def edit_specialization_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования специализации"""
    await state.set_state(SettingsStates.enter_specialization)
    await callback.message.edit_text("✏️ Введите новую специализацию (минимум 2 символа):")
    await callback.answer()


@router.callback_query(F.data == "edit_phone")
async def edit_phone_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования телефона"""
    await state.set_state(SettingsStates.enter_phone)
    await callback.message.edit_text("✏️ Введите новый телефон (или /skip для удаления):")
    await callback.answer()


@router.callback_query(F.data == "edit_address")
async def edit_address_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования адреса"""
    await state.set_state(SettingsStates.enter_address)
    await callback.message.edit_text("✏️ Введите новый адрес (или /skip для удаления):")
    await callback.answer()


@router.callback_query(F.data == "edit_location")
async def edit_location_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования геолокации"""
    await state.set_state(SettingsStates.enter_location)
    await callback.message.edit_text(
        "📍 Отправьте геолокацию клиники (скрепка → Местоположение) или /skip для удаления:"
    )
    await callback.answer()


@router.callback_query(F.data == "edit_photo")
async def edit_photo_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования фото"""
    await state.set_state(SettingsStates.enter_photo)
    await callback.message.edit_text("📷 Отправьте новое фото или /skip для удаления:")
    await callback.answer()


@router.callback_query(F.data == "edit_reminder", flags={"tier": 1})
async def edit_reminder_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало изменения времени напоминания (Standard/Premium)"""
    current = get_reminder_minutes(user)
    builder = InlineKeyboardBuilder()
    for mins in [15, 30, 60, 120, 180]:
        label = f"{mins} мин"
        if mins == current:
            label = f"✓ {label}"
        builder.button(text=label, callback_data=f"reminder_{mins}")
    builder.button(text="← Назад", callback_data="settings_reminder_back")
    builder.adjust(2, 2, 2, 1)
    await callback.message.edit_text(
        f"⏰ **Напоминание до записи**\n\n"
        f"Сейчас: за {current} мин.\n"
        f"Выберите новое значение:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reminder_"))
async def process_edit_reminder(callback: CallbackQuery, user: User, state: FSMContext, db_session):
    """Сохранение времени напоминания"""
    if user.subscription_tier < 1:
        await callback.answer("❌ Доступно в Standard и Premium", show_alert=True)
        return
    try:
        mins = int(callback.data.replace("reminder_", ""))
        if mins < 5 or mins > 1440:
            raise ValueError("out of range")
    except (ValueError, TypeError):
        await callback.answer("❌ Неверное значение", show_alert=True)
        return

    settings = dict(user.settings or {})
    settings["reminder_minutes"] = mins
    user.settings = settings
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await callback.message.edit_text(f"✅ Напоминание: за {mins} мин до записи")
    await callback.message.answer(_get_settings_text(user), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings_reminder_back")
async def reminder_back(callback: CallbackQuery, user: User, state: FSMContext):
    """Назад из настроек напоминания"""
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await callback.message.edit_text(_get_settings_text(user), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "edit_timezone")
async def edit_timezone_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало редактирования часового пояса"""
    await state.set_state(SettingsStates.enter_timezone)
    timezones = get_common_timezones()
    builder = InlineKeyboardBuilder()
    for tz_name, tz_display in timezones:
        builder.button(text=tz_display, callback_data=f"tz_{tz_name}")
    builder.adjust(1)
    await callback.message.edit_text("🌍 Выберите часовой пояс:", reply_markup=builder.as_markup())
    await callback.answer()


# Обработчики ввода значений
@router.message(StateFilter(SettingsStates.enter_full_name), F.text)
async def process_edit_full_name(message: Message, user: User, state: FSMContext, db_session):
    """Обработка нового ФИО"""
    text = message.text.strip()
    if len(text) < 3:
        await message.answer("❌ ФИО должно содержать минимум 3 символа. Попробуйте снова:")
        return
    user.full_name = text
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ ФИО обновлено!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_specialization), F.text)
async def process_edit_specialization(message: Message, user: User, state: FSMContext, db_session):
    """Обработка новой специализации"""
    text = message.text.strip()
    if len(text) < 2:
        await message.answer("❌ Специализация должна содержать минимум 2 символа. Попробуйте снова:")
        return
    user.specialization = text
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Специализация обновлена!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_phone), F.text)
async def process_edit_phone(message: Message, user: User, state: FSMContext, db_session):
    """Обработка нового телефона"""
    if message.text.strip().lower() == "/skip":
        user.phone = None
    else:
        user.phone = message.text.strip()
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Телефон обновлён!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_address), F.text)
async def process_edit_address(message: Message, user: User, state: FSMContext, db_session):
    """Обработка нового адреса"""
    if message.text.strip().lower() == "/skip":
        user.address = None
    else:
        user.address = message.text.strip()
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Адрес обновлён!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_location), F.location)
async def process_edit_location(message: Message, user: User, state: FSMContext, db_session):
    """Обработка новой геолокации"""
    loc = message.location
    user.location_lat = loc.latitude
    user.location_lon = loc.longitude
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Геолокация обновлена!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_location), F.text)
async def process_edit_location_skip(message: Message, user: User, state: FSMContext, db_session):
    """Пропуск геолокации"""
    if message.text.strip().lower() != "/skip":
        await message.answer("❌ Отправьте геолокацию или /skip:")
        return
    user.location_lat = None
    user.location_lon = None
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Геолокация удалена.", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_photo), F.photo)
async def process_edit_photo(message: Message, user: User, state: FSMContext, db_session):
    """Обработка нового фото"""
    photo = message.photo[-1]
    user.photo_url = photo.file_id
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Фото обновлено!", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.message(StateFilter(SettingsStates.enter_photo), F.text)
async def process_edit_photo_skip(message: Message, user: User, state: FSMContext, db_session):
    """Пропуск фото"""
    if message.text.strip().lower() != "/skip":
        await message.answer("❌ Отправьте фото или /skip:")
        return
    user.photo_url = None
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await message.answer("✅ Фото удалено.", reply_markup=get_settings_keyboard())
    await message.answer(_get_settings_text(user), reply_markup=builder.as_markup())


@router.callback_query(StateFilter(SettingsStates.enter_timezone), F.data.startswith("tz_"))
async def process_edit_timezone(callback: CallbackQuery, user: User, state: FSMContext, db_session):
    """Обработка выбора часового пояса"""
    timezone_name = callback.data.replace("tz_", "")
    user.timezone = timezone_name
    await db_session.commit()
    await state.clear()
    builder = _get_settings_inline_keyboard(user)
    await callback.message.edit_text(f"✅ Часовой пояс обновлён!")
    await callback.message.answer(_get_settings_text(user), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings_back")
async def settings_back(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    assistant_permissions: dict,
    state: FSMContext,
):
    """Возврат в главное меню из настроек"""
    await state.clear()
    tier_names = {0: "Basic", 1: "Standard", 2: "Premium"}
    tier_name = tier_names.get(effective_doctor.subscription_tier, "Basic")
    text = (
        f"📋 Главное меню\n\n"
        f"👤 {user.full_name}\n"
        f"🏥 {effective_doctor.specialization or 'Не указано'}\n"
        f"⭐ Уровень подписки: {tier_name}\n\n"
        f"Выберите действие:"
    )
    await callback.message.answer(text, reply_markup=get_main_menu_keyboard(user, effective_doctor, assistant_permissions))
    await callback.answer()


@router.callback_query(F.data == "settings_delete_account")
async def settings_delete_account_confirm(callback: CallbackQuery, user: User):
    """Подтверждение удаления аккаунта."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить аккаунт", callback_data="settings_delete_confirm")
    builder.button(text="❌ Отмена", callback_data="settings_back")
    builder.adjust(1)
    await callback.message.edit_text(
        "🗑 **Удалить аккаунт?**\n\n"
        "Будут безвозвратно удалены все ваши данные: пациенты, записи, финансы, настройки. "
        "После удаления вы сможете снова нажать /start и зарегистрироваться заново.\n\n"
        "Вы уверены?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_delete_confirm")
async def settings_delete_confirm_do(
    callback: CallbackQuery,
    user: User,
    db_session: AsyncSession,
):
    """Удалить аккаунт текущего пользователя."""
    ok = await delete_user_from_db(db_session, user)
    if ok:
        await callback.message.edit_text(
            "✅ Аккаунт удалён.\n\n"
            "Нажмите /start для повторной регистрации."
        )
    else:
        await callback.message.edit_text("❌ Не удалось удалить аккаунт. Обратитесь к администратору.")
    await callback.answer()
