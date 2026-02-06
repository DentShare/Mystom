from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, Location
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.states.registration import RegistrationStates
from app.services.timezone import get_common_timezones

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, user: User, state: FSMContext):
    """Обработчик команды /start"""
    # Проверяем, заполнена ли регистрация
    if user.full_name and user.full_name != "Не указано" and user.specialization:
        # Пользователь уже зарегистрирован
        await message.answer(
            f"👋 Добро пожаловать, {user.full_name}!\n\n"
            f"Ваш уровень подписки: {_get_tier_name(user.subscription_tier)}\n\n"
            f"Используйте /menu для доступа к главному меню."
        )
        await state.clear()
        return
    
    # Начинаем регистрацию
    await message.answer(
        "👋 Добро пожаловать в MiniStom!\n\n"
        "Я помогу вам организовать работу с пациентами.\n\n"
        "Давайте начнем регистрацию. Пожалуйста, введите ваше ФИО:"
    )
    await state.set_state(RegistrationStates.enter_full_name)


@router.message(StateFilter(RegistrationStates.enter_full_name))
async def process_full_name(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка ввода ФИО"""
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("❌ ФИО должно содержать минимум 3 символа. Попробуйте еще раз:")
        return
    
    user.full_name = full_name
    await db_session.commit()
    
    await message.answer("✅ ФИО сохранено!\n\nТеперь введите вашу специализацию:")
    await state.set_state(RegistrationStates.enter_specialization)


@router.message(StateFilter(RegistrationStates.enter_specialization))
async def process_specialization(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка ввода специализации"""
    specialization = message.text.strip()
    if len(specialization) < 2:
        await message.answer("❌ Специализация должна содержать минимум 2 символа. Попробуйте еще раз:")
        return
    
    user.specialization = specialization
    await db_session.commit()
    
    await message.answer("✅ Специализация сохранена!\n\nВведите ваш телефон (или отправьте /skip для пропуска):")
    await state.set_state(RegistrationStates.enter_phone)


@router.message(StateFilter(RegistrationStates.enter_phone))
async def process_phone(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка ввода телефона"""
    if message.text and message.text.strip().lower() == "/skip":
        await message.answer("✅ Телефон пропущен.\n\nВведите адрес клиники (или отправьте /skip):")
        await state.set_state(RegistrationStates.enter_address)
        return
    
    phone = message.text.strip() if message.text else ""
    if phone:
        user.phone = phone
        await db_session.commit()
    
    await message.answer("✅ Телефон сохранен!\n\nВведите адрес клиники (или отправьте /skip):")
    await state.set_state(RegistrationStates.enter_address)


@router.message(StateFilter(RegistrationStates.enter_address))
async def process_address(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка ввода адреса"""
    if message.text and message.text.strip().lower() == "/skip":
        await message.answer(
            "✅ Адрес пропущен.\n\n"
            "Отправьте геолокацию клиники (нажмите на скрепку 📎 и выберите 'Местоположение') "
            "или отправьте /skip:"
        )
        await state.set_state(RegistrationStates.enter_location)
        return
    
    address = message.text.strip() if message.text else ""
    if address:
        user.address = address
        await db_session.commit()
    
    await message.answer(
        "✅ Адрес сохранен!\n\n"
        "Отправьте геолокацию клиники (нажмите на скрепку 📎 и выберите 'Местоположение') "
        "или отправьте /skip:"
    )
    await state.set_state(RegistrationStates.enter_location)


@router.message(StateFilter(RegistrationStates.enter_location), F.location)
async def process_location(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка геолокации"""
    location: Location = message.location
    user.location_lat = location.latitude
    user.location_lon = location.longitude
    await db_session.commit()
    
    await message.answer(
        "✅ Геолокация сохранена!\n\n"
        "Отправьте ваше фото (или отправьте /skip):"
    )
    await state.set_state(RegistrationStates.enter_photo)


@router.message(StateFilter(RegistrationStates.enter_location))
async def process_location_skip(message: Message, user: User, state: FSMContext):
    """Пропуск геолокации"""
    if message.text and message.text.strip().lower() == "/skip":
        await message.answer(
            "✅ Геолокация пропущена.\n\n"
            "Отправьте ваше фото (или отправьте /skip):"
        )
        await state.set_state(RegistrationStates.enter_photo)
    else:
        await message.answer("❌ Пожалуйста, отправьте геолокацию или /skip")


@router.message(StateFilter(RegistrationStates.enter_photo), F.photo)
async def process_photo(message: Message, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка фото — сохраняем file_id для Telegram API"""
    photo = message.photo[-1]  # Берем фото наибольшего размера
    user.photo_url = photo.file_id  # file_id работает с send_photo
    await db_session.commit()
    
    await _ask_timezone(message, state)


@router.message(StateFilter(RegistrationStates.enter_photo))
async def process_photo_skip(message: Message, user: User, state: FSMContext):
    """Пропуск фото"""
    if message.text and message.text.strip().lower() == "/skip":
        await _ask_timezone(message, state)
    else:
        await message.answer("❌ Пожалуйста, отправьте фото или /skip")


async def _ask_timezone(message: Message, state: FSMContext):
    """Запрос часового пояса"""
    timezones = get_common_timezones()
    builder = InlineKeyboardBuilder()
    
    for tz_name, tz_display in timezones:
        builder.button(text=tz_display, callback_data=f"tz_{tz_name}")
    
    builder.adjust(1)
    
    await message.answer(
        "✅ Фото сохранено!\n\n"
        "Выберите ваш часовой пояс:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(RegistrationStates.enter_timezone)


@router.callback_query(StateFilter(RegistrationStates.enter_timezone), F.data.startswith("tz_"))
async def process_timezone(callback: CallbackQuery, user: User, state: FSMContext, db_session: AsyncSession):
    """Обработка выбора часового пояса"""
    timezone_name = callback.data.replace("tz_", "")
    user.timezone = timezone_name
    await db_session.commit()
    
    await callback.message.edit_text(
        f"✅ Регистрация завершена!\n\n"
        f"👤 ФИО: {user.full_name}\n"
        f"🏥 Специализация: {user.specialization}\n"
        f"📞 Телефон: {user.phone or 'Не указан'}\n"
        f"📍 Адрес: {user.address or 'Не указан'}\n"
        f"🌍 Часовой пояс: {timezone_name}\n\n"
        f"Используйте /menu для доступа к главному меню."
    )
    await callback.answer()
    await state.clear()


def _get_tier_name(tier: int) -> str:
    """Получить название уровня подписки"""
    names = {0: "Basic", 1: "Standard", 2: "Premium"}
    return names.get(tier, "Basic")

