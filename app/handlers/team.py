"""
Раздел «Моя команда»: врач приглашает ассистентов и настраивает права.
Ассистент привязывается по коду и может отвязаться.
"""
import logging
import secrets
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database.models import User, DoctorAssistant, InviteCode
from app.utils.permissions import (
    default_permissions,
    normalize_permissions,
    ALL_FEATURES,
    FEATURE_LABELS,
    LEVEL_NONE,
    LEVEL_VIEW,
    LEVEL_EDIT,
)

router = Router(name="team")
log = logging.getLogger("app.handlers.team")


def _is_owner(user: User) -> bool:
    return getattr(user, "role", "owner") == "owner"


def _code_str() -> str:
    return secrets.token_hex(3).upper()  # 6 символов


@router.message(F.text == "👥 Моя команда")
@router.message(Command("team"))
async def cmd_team(
    message: Message,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
    state: FSMContext,
):
    """Вход в раздел: для владельца — список ассистентов, для ассистента — информация о привязке."""
    await state.clear()
    if not _is_owner(user):
        # Ассистент: показать, с кем привязан, и кнопку отвязаться
        if user.owner_id != effective_doctor.id:
            await message.answer("Вы не привязаны к врачу. Используйте кнопку «Привязаться к врачу» или введите код приглашения.")
            return
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="🔓 Отвязаться от врача", callback_data="team_unbind_me")
        await message.answer(
            f"Вы работаете с врачом: **{effective_doctor.full_name}**.\n\n"
            "Все данные (календарь, пациенты и т.д.) синхронизированы с его аккаунтом. Ваш доступ ограничен настройками врача.",
            reply_markup=builder.as_markup(),
        )
        return

    if user.id != effective_doctor.id:
        await message.answer("Раздел «Моя команда» доступен только владельцу аккаунта.")
        return

    # Владелец: список ассистентов
    stmt = select(DoctorAssistant).where(DoctorAssistant.doctor_id == user.id)
    result = await db_session.execute(stmt)
    links = list(result.scalars().all())
    if not links:
        text = "👥 **Моя команда**\n\nПока нет привязанных ассистентов. Создайте код приглашения и передайте его ассистенту."
    else:
        text = "👥 **Моя команда**\n\nВаши ассистенты:\n"
        for link in links:
            await db_session.refresh(link.assistant_user)
            text += f"\n• {link.assistant_user.full_name} (ID: {link.assistant_user.telegram_id})"
            perms = link.permissions or {}
            view_edit = [k for k in ALL_FEATURES if perms.get(k) == LEVEL_EDIT]
            view_only = [k for k in ALL_FEATURES if perms.get(k) == LEVEL_VIEW]
            if view_edit or view_only:
                text += f"\n  Редактирование: {', '.join(view_edit) or '—'}; просмотр: {', '.join(view_only) or '—'}"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Пригласить ассистента", callback_data="team_invite")
    for link in links:
        builder.button(
            text=f"⚙️ {link.assistant_user.full_name}",
            callback_data=f"team_asst_{link.assistant_id}",
        )
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "team_invite")
async def team_invite(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Создать код приглашения."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    code = _code_str()
    invite = InviteCode(
        doctor_id=user.id,
        code=code,
        permissions=default_permissions(),
    )
    db_session.add(invite)
    await db_session.commit()
    await callback.message.answer(
        f"Код приглашения: **`{code}`**\n\n"
        "Передайте его ассистенту. Он должен ввести код в боте (кнопка «Привязаться к врачу» или команда /bind с кодом).\n"
        "Код действует до использования.",
    )
    await callback.answer("Код создан")


@router.callback_query(F.data.startswith("team_asst_"))
async def team_asst_menu(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Меню по ассистенту: изменить права или отвязать."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    assistant_id = int(callback.data.split("_")[-1])
    stmt = select(DoctorAssistant).where(
        DoctorAssistant.doctor_id == user.id,
        DoctorAssistant.assistant_id == assistant_id,
    )
    res = await db_session.execute(stmt)
    link = res.scalar_one_or_none()
    if not link:
        await callback.answer("Ассистент не найден.", show_alert=True)
        return
    await db_session.refresh(link.assistant_user)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить права", callback_data=f"team_edit_{assistant_id}")
    builder.button(text="🔓 Отвязать", callback_data=f"team_unbind_{assistant_id}")
    builder.button(text="⬅️ Назад", callback_data="team_back")
    builder.adjust(1)
    perms = link.permissions or {}
    lines = [f"{FEATURE_LABELS.get(k, k)}: {perms.get(k, LEVEL_NONE)}" for k in ALL_FEATURES]
    await callback.message.edit_text(
        f"Ассистент: **{link.assistant_user.full_name}**\n\nПрава:\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "team_back")
async def team_back(callback: CallbackQuery, user: User, effective_doctor: User, db_session: AsyncSession):
    """Вернуться к списку команды."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer()
        return
    stmt = select(DoctorAssistant).where(DoctorAssistant.doctor_id == user.id)
    result = await db_session.execute(stmt)
    links = list(result.scalars().all())
    text = "👥 **Моя команда**\n\nВаши ассистенты:\n" if links else "👥 **Моя команда**\n\nПока нет привязанных ассистентов."
    for link in links:
        await db_session.refresh(link.assistant_user)
        text += f"\n• {link.assistant_user.full_name}"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Пригласить ассистента", callback_data="team_invite")
    for link in links:
        builder.button(text=f"⚙️ {link.assistant_user.full_name}", callback_data=f"team_asst_{link.assistant_id}")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("team_edit_"))
async def team_edit_permissions(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Изменить права ассистента: цикл none -> view -> edit -> none."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    assistant_id = int(callback.data.split("_")[-1])
    stmt = select(DoctorAssistant).where(
        DoctorAssistant.doctor_id == user.id,
        DoctorAssistant.assistant_id == assistant_id,
    )
    res = await db_session.execute(stmt)
    link = res.scalar_one_or_none()
    if not link:
        await callback.answer("Не найден.", show_alert=True)
        return
    perms = normalize_permissions(link.permissions)
    # Rotate level for each feature: build inline keyboard with callback_data team_perm_<asst_id>_<feature>_<next_level>
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for feat in ALL_FEATURES:
        level = perms.get(feat, LEVEL_NONE)
        next_level = {LEVEL_NONE: LEVEL_VIEW, LEVEL_VIEW: LEVEL_EDIT, LEVEL_EDIT: LEVEL_NONE}.get(level, LEVEL_NONE)
        builder.button(
            text=f"{FEATURE_LABELS.get(feat, feat)}: {level} → {next_level}",
            callback_data=f"team_perm_{assistant_id}_{feat}",
        )
    builder.button(text="💾 Сохранить", callback_data=f"team_save_{assistant_id}")
    builder.button(text="⬅️ Назад", callback_data=f"team_asst_{assistant_id}")
    builder.adjust(1)
    await callback.message.edit_text(
        "Нажмите на раздел, чтобы сменить уровень доступа (none → view → edit → none). Затем «Сохранить».",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("team_perm_"))
async def team_perm_toggle(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Переключить уровень доступа по одному разделу."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer()
        return
    parts = callback.data.split("_")
    assistant_id = int(parts[2])
    feature = "_".join(parts[3:]) if len(parts) > 3 else parts[3]
    if feature not in ALL_FEATURES:
        await callback.answer()
        return
    stmt = select(DoctorAssistant).where(
        DoctorAssistant.doctor_id == user.id,
        DoctorAssistant.assistant_id == assistant_id,
    )
    res = await db_session.execute(stmt)
    link = res.scalar_one_or_none()
    if not link:
        await callback.answer("Не найден.", show_alert=True)
        return
    perms = normalize_permissions(link.permissions)
    level = perms.get(feature, LEVEL_NONE)
    next_level = {LEVEL_NONE: LEVEL_VIEW, LEVEL_VIEW: LEVEL_EDIT, LEVEL_EDIT: LEVEL_NONE}.get(level, LEVEL_NONE)
    perms[feature] = next_level
    link.permissions = perms
    await db_session.commit()
    # Refresh the edit screen
    builder = InlineKeyboardBuilder()
    for feat in ALL_FEATURES:
        lv = perms.get(feat, LEVEL_NONE)
        nxt = {LEVEL_NONE: LEVEL_VIEW, LEVEL_VIEW: LEVEL_EDIT, LEVEL_EDIT: LEVEL_NONE}.get(lv, LEVEL_NONE)
        builder.button(
            text=f"{FEATURE_LABELS.get(feat, feat)}: {lv} → {nxt}",
            callback_data=f"team_perm_{assistant_id}_{feat}",
        )
    builder.button(text="💾 Сохранить", callback_data=f"team_save_{assistant_id}")
    builder.button(text="⬅️ Назад", callback_data=f"team_asst_{assistant_id}")
    builder.adjust(1)
    await callback.message.edit_text(
        "Нажмите на раздел, чтобы сменить уровень доступа. Затем «Сохранить».",
        reply_markup=builder.as_markup(),
    )
    await callback.answer(f"{feature}: {next_level}")


@router.callback_query(F.data.startswith("team_save_"))
async def team_save_permissions(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Сохранить права и вернуться к ассистенту."""
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer()
        return
    assistant_id = int(callback.data.split("_")[-1])
    await db_session.commit()
    await callback.answer("Сохранено")
    # Redirect to team_asst_ menu
    callback.data = f"team_asst_{assistant_id}"
    await team_asst_menu(callback, user, effective_doctor, db_session)


@router.callback_query(F.data.startswith("team_unbind_"))
async def team_unbind(
    callback: CallbackQuery,
    user: User,
    effective_doctor: User,
    db_session: AsyncSession,
):
    """Отвязать ассистента (врач) или отвязаться самому (ассистент)."""
    if callback.data == "team_unbind_me":
        # Ассистент отвязывается сам
        if _is_owner(user) or not user.owner_id:
            await callback.answer("Вы не привязаны к врачу.", show_alert=True)
            return
        stmt = delete(DoctorAssistant).where(
            DoctorAssistant.assistant_id == user.id,
            DoctorAssistant.doctor_id == user.owner_id,
        )
        await db_session.execute(stmt)
        user.role = "owner"
        user.owner_id = None
        await db_session.commit()
        await callback.message.edit_text("Вы отвязаны от врача. Теперь вы работаете со своим аккаунтом.")
        await callback.answer("Отвязано")
        return

    # Врач отвязывает ассистента
    if not _is_owner(user) or user.id != effective_doctor.id:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    assistant_id = int(callback.data.split("_")[-1])
    stmt = select(DoctorAssistant).where(
        DoctorAssistant.doctor_id == user.id,
        DoctorAssistant.assistant_id == assistant_id,
    )
    res = await db_session.execute(stmt)
    link = res.scalar_one_or_none()
    if not link:
        await callback.answer("Не найден.", show_alert=True)
        return
    asst_user = link.assistant_user
    await db_session.delete(link)
    asst_user.role = "owner"
    asst_user.owner_id = None
    await db_session.commit()
    await callback.message.edit_text(f"Ассистент {asst_user.full_name} отвязан.")
    await callback.answer("Отвязано")


# Привязка по коду
@router.message(F.text == "🔗 Привязаться к врачу")
@router.message(Command("bind"))
async def bind_start(
    message: Message,
    user: User,
    state: FSMContext,
):
    """Начать привязку: если уже привязан — сообщить; иначе попросить ввести код."""
    if getattr(user, "role", "owner") == "assistant" and user.owner_id:
        await message.answer("Вы уже привязаны к врачу. Раздел «Моя команда» покажет информацию.")
        return
    if message.text and message.text.startswith("/bind ") and len(message.text.split()) >= 2:
        code = message.text.split(maxsplit=1)[1].strip().upper()
        await _do_bind(message, user, code, state)
        return
    await state.set_state(TeamStates.enter_invite_code)
    await message.answer("Введите код приглашения от врача (6 символов):")


@router.message(TeamStates.enter_invite_code, F.text)
async def bind_enter_code(
    message: Message,
    user: User,
    db_session: AsyncSession,
    state: FSMContext,
):
    """Обработка введённого кода приглашения."""
    if not message.text:
        return
    code = message.text.strip().upper().replace(" ", "")
    if len(code) < 4:
        await message.answer("Код слишком короткий. Введите код, который дал вам врач.")
        return
    await _do_bind(message, user, code, state)


async def _do_bind(
    message: Message,
    user: User,
    code: str,
    state: FSMContext,
):
    from app.database.session import async_session_maker
    await state.clear()
    async with async_session_maker() as db_session:
        stmt = select(InviteCode).where(InviteCode.code == code)
        res = await db_session.execute(stmt)
        invite = res.scalar_one_or_none()
        if not invite:
            await message.answer("Код не найден или уже использован. Проверьте код и попробуйте снова.")
            return
        doctor_id = invite.doctor_id
        perms = normalize_permissions(invite.permissions)
        link = DoctorAssistant(
            doctor_id=doctor_id,
            assistant_id=user.id,
            permissions=perms,
        )
        db_session.add(link)
        user.role = "assistant"
        user.owner_id = doctor_id
        await db_session.delete(invite)
        await db_session.commit()
    await message.answer(
        "Вы успешно привязаны к врачу. Теперь в меню доступны разделы в соответствии с выданными правами. "
        "Все данные синхронизированы с аккаунтом врача."
    )
