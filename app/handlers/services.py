"""Управление услугами (Прайс-лист) — просмотр для всех, редактирование Premium"""
from aiogram import Router, F  # pyright: ignore[reportMissingImports]
from aiogram.filters import StateFilter  # pyright: ignore[reportMissingImports]
from aiogram.fsm.context import FSMContext  # pyright: ignore[reportMissingImports]
from aiogram.fsm.state import State, StatesGroup  # pyright: ignore[reportMissingImports]
from aiogram.types import Message, CallbackQuery  # pyright: ignore[reportMissingImports]
from aiogram.utils.keyboard import InlineKeyboardBuilder  # pyright: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import AsyncSession  # pyright: ignore[reportMissingImports]
from sqlalchemy import select, delete  # pyright: ignore[reportMissingImports]

from app.database.models import User, Service
from app.utils.formatters import format_money
from app.services.service_service import (
    get_categories,
    get_services_by_category,
    ensure_default_services,
    get_service_by_id,
    CATEGORIES,
)
from app.keyboards.main import get_main_menu_keyboard

router = Router(name="services")


class ServiceEditStates(StatesGroup):
    select_category = State()
    select_action = State()
    enter_name = State()
    enter_price = State()
    enter_duration = State()


@router.message(F.text == "💵 Прайс-лист", flags={"tier": 0})
async def cmd_price_list(message: Message, user: User, db_session: AsyncSession):
    """Прайс-лист — просмотр для всех, редактирование только Premium"""
    await ensure_default_services(db_session, user.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"price_cat_{cat_id}")
    builder.adjust(2)

    hint = (
        "Выберите категорию для просмотра и редактирования услуг:"
        if user.subscription_tier >= 2
        else "Выберите категорию для просмотра услуг (редактирование доступно в Premium):"
    )
    await message.answer(
        f"💵 **Прайс-лист**\n\n{hint}",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("price_cat_"))
async def price_list_category(
    callback: CallbackQuery,
    user: User,
    db_session: AsyncSession
):
    """Просмотр услуг категории (редактирование только Premium)"""
    category = callback.data.replace("price_cat_", "")
    services = await get_services_by_category(db_session, user.id, category)
    cat_name, cat_emoji = CATEGORIES.get(category, ("", ""))

    lines = [f"💵 **{cat_emoji} {cat_name}**\n"]
    for svc in services:
        dur = getattr(svc, 'duration_minutes', 30)
        lines.append(f"• {svc.name} — {format_money(svc.price)} ({dur} мин)")
    if not services:
        lines.append("_Услуг пока нет_")

    builder = InlineKeyboardBuilder()
    if user.subscription_tier >= 1:
        # Standard+: кнопки редактирования (длительность — Standard, остальное — Premium)
        for svc in services:
            text = f"✏️ {svc.name[:30]}"
            builder.button(text=text, callback_data=f"price_edit_{svc.id}")
        if user.subscription_tier >= 2:
            builder.button(text="➕ Добавить услугу", callback_data=f"price_add_{category}")
    builder.button(text="← Назад", callback_data="price_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "price_back")
async def price_back(callback: CallbackQuery, user: User, db_session: AsyncSession):
    """Назад к списку категорий"""
    await ensure_default_services(db_session, user.id)
    categories = await get_categories()

    builder = InlineKeyboardBuilder()
    for cat_id, name, emoji in categories:
        builder.button(text=f"{emoji} {name}", callback_data=f"price_cat_{cat_id}")
    builder.adjust(2)

    hint = (
        "Выберите категорию для просмотра и редактирования:"
        if user.subscription_tier >= 2
        else "Выберите категорию для просмотра услуг:"
    )
    await callback.message.edit_text(
        f"💵 **Прайс-лист**\n\n{hint}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("price_add_"))
async def price_add_service(
    callback: CallbackQuery,
    user: User,
    state: FSMContext
):
    """Добавление новой услуги (только Premium)"""
    if user.subscription_tier < 2:
        await callback.answer("❌ Редактирование прайс-листа доступно в Premium", show_alert=True)
        return
    category = callback.data.replace("price_add_", "")
    await state.update_data(service_action="add", service_category=category)
    await callback.message.edit_text("📝 Введите название новой услуги:")
    await state.set_state(ServiceEditStates.enter_name)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^price_edit_\d+$"))
async def price_edit_service(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Редактирование услуги — выбор действия (Standard+: длительность, Premium: всё)"""
    if user.subscription_tier < 1:
        await callback.answer("❌ Редактирование доступно в Standard и Premium", show_alert=True)
        return
    service_id = int(callback.data.replace("price_edit_", ""))
    service = await get_service_by_id(db_session, service_id, user.id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    await state.update_data(
        service_action="edit",
        service_id=service_id,
        service_category=service.category
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="⏱ Изменить длительность", callback_data="price_edit_duration")
    if user.subscription_tier >= 2:
        builder.button(text="✏️ Изменить название", callback_data="price_edit_name")
        builder.button(text="💰 Изменить цену", callback_data="price_edit_price")
        builder.button(text="🗑 Удалить", callback_data="price_delete")
    builder.button(text="← Назад", callback_data=f"price_cat_{service.category}")
    builder.adjust(1)

    dur = getattr(service, 'duration_minutes', 30)
    await callback.message.edit_text(
        f"📋 **{service.name}** — {format_money(service.price)} ({dur} мин)\n\nВыберите действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "price_edit_name")
async def price_edit_name_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало изменения названия (только Premium)"""
    if user.subscription_tier < 2:
        await callback.answer("❌ Редактирование прайс-листа доступно в Premium", show_alert=True)
        return
    await callback.message.edit_text("📝 Введите новое название услуги:")
    await state.set_state(ServiceEditStates.enter_name)
    await callback.answer()


@router.callback_query(F.data == "price_edit_price")
async def price_edit_price_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало изменения цены (только Premium)"""
    if user.subscription_tier < 2:
        await callback.answer("❌ Редактирование прайс-листа доступно в Premium", show_alert=True)
        return
    await callback.message.edit_text("💰 Введите новую цену в сумах (число):")
    await state.set_state(ServiceEditStates.enter_price)
    await callback.answer()


@router.callback_query(F.data == "price_edit_duration")
async def price_edit_duration_start(callback: CallbackQuery, user: User, state: FSMContext):
    """Начало изменения длительности (Standard/Premium)"""
    if user.subscription_tier < 1:
        await callback.answer("❌ Редактирование длительности доступно в Standard и Premium", show_alert=True)
        return
    await callback.message.edit_text("⏱ Введите длительность услуги в минутах (число, например 30 или 60):")
    await state.set_state(ServiceEditStates.enter_duration)
    await callback.answer()


@router.callback_query(F.data == "price_delete")
async def price_delete_service(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Удаление услуги (только Premium)"""
    if user.subscription_tier < 2:
        await callback.answer("❌ Редактирование прайс-листа доступно в Premium", show_alert=True)
        return
    data = await state.get_data()
    service_id = data.get("service_id")
    category = data.get("service_category")

    stmt = delete(Service).where(
        Service.id == service_id,
        Service.doctor_id == user.id
    )
    await db_session.execute(stmt)
    await db_session.commit()
    await state.clear()

    # Возврат к списку услуг категории
    services = await get_services_by_category(db_session, user.id, category)
    cat_name, cat_emoji = CATEGORIES.get(category, ("", ""))

    lines = [f"💵 **{cat_emoji} {cat_name}**\n"]
    for svc in services:
        dur = getattr(svc, 'duration_minutes', 30)
        lines.append(f"• {svc.name} — {format_money(svc.price)} ({dur} мин)")
    if not services:
        lines.append("_Услуг пока нет_")

    builder = InlineKeyboardBuilder()
    if user.subscription_tier >= 1:
        for svc in services:
            builder.button(text=f"✏️ {svc.name[:30]}", callback_data=f"price_edit_{svc.id}")
        if user.subscription_tier >= 2:
            builder.button(text="➕ Добавить услугу", callback_data=f"price_add_{category}")
    builder.button(text="← Назад", callback_data="price_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "✅ Услуга удалена.\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.message(StateFilter(ServiceEditStates.enter_name), F.text)
async def process_service_name(
    message: Message,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка названия услуги (только Premium)"""
    if user.subscription_tier < 2:
        await state.clear()
        await message.answer("❌ Редактирование прайс-листа доступно в Premium")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Название должно быть минимум 2 символа:")
        return

    data = await state.get_data()
    action = data.get("service_action")
    category = data.get("service_category")

    if action == "add":
        await state.update_data(service_name=name)
        await message.answer("💰 Введите цену в сумах (число):")
        await state.set_state(ServiceEditStates.enter_price)
    else:
        service_id = data.get("service_id")
        stmt = select(Service).where(
            Service.id == service_id,
            Service.doctor_id == user.id
        )
        result = await db_session.execute(stmt)
        service = result.scalar_one_or_none()
        if service:
            service.name = name
            await db_session.commit()
        await state.clear()
        await message.answer(f"✅ Название обновлено: {name}")


@router.message(StateFilter(ServiceEditStates.enter_price), F.text)
async def process_service_price(
    message: Message,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка цены услуги (только Premium)"""
    if user.subscription_tier < 2:
        await state.clear()
        await message.answer("❌ Редактирование прайс-листа доступно в Premium")
        return
    try:
        price = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if price < 0:
            raise ValueError("Цена не может быть отрицательной")
    except ValueError:
        await message.answer("❌ Введите корректную цену (число):")
        return

    data = await state.get_data()
    action = data.get("service_action")
    category = data.get("service_category")

    if action == "add":
        await state.update_data(service_price=price)
        await message.answer("⏱ Введите длительность в минутах (число, например 30):")
        await state.set_state(ServiceEditStates.enter_duration)
        return
    else:
        service_id = data.get("service_id")
        stmt = select(Service).where(
            Service.id == service_id,
            Service.doctor_id == user.id
        )
        result = await db_session.execute(stmt)
        service = result.scalar_one_or_none()
        if service:
            service.price = price
            await db_session.commit()
            await message.answer(f"✅ Цена обновлена: {service.name} — {format_money(price)}")
        await state.clear()


@router.message(StateFilter(ServiceEditStates.enter_duration), F.text)
async def process_service_duration(
    message: Message,
    user: User,
    state: FSMContext,
    db_session: AsyncSession
):
    """Обработка длительности услуги (Standard+: edit, Premium: add)"""
    if user.subscription_tier < 1:
        await state.clear()
        await message.answer("❌ Редактирование длительности доступно в Standard и Premium")
        return
    try:
        duration = int(message.text.strip())
        if duration < 5 or duration > 480:
            raise ValueError("Длительность от 5 до 480 минут")
    except ValueError:
        await message.answer("❌ Введите число от 5 до 480 (минуты):")
        return

    data = await state.get_data()
    action = data.get("service_action")
    category = data.get("service_category")

    if action == "add":
        name = data.get("service_name")
        price = data.get("service_price", 0)
        services = await get_services_by_category(db_session, user.id, category)
        sort_order = max((s.sort_order for s in services), default=-1) + 1
        service = Service(
            doctor_id=user.id,
            category=category,
            name=name,
            price=price,
            duration_minutes=duration,
            sort_order=sort_order,
        )
        db_session.add(service)
        await db_session.commit()
        await message.answer(f"✅ Услуга добавлена: {name} — {format_money(price)} ({duration} мин)")
    else:
        service_id = data.get("service_id")
        stmt = select(Service).where(
            Service.id == service_id,
            Service.doctor_id == user.id
        )
        result = await db_session.execute(stmt)
        service = result.scalar_one_or_none()
        if service:
            service.duration_minutes = duration
            await db_session.commit()
            await message.answer(f"✅ Длительность обновлена: {service.name} — {duration} мин")

    await state.clear()
