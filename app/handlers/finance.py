from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database.models import User, Patient, Treatment, Appointment
from app.utils.formatters import format_money, treatment_effective_price
from app.utils.permissions import can_access, FEATURE_FINANCE

router = Router(name="finance")


def _treatment_debt(t: Treatment) -> float:
    """Долг по позиции: итоговая цена минус оплачено."""
    eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
    paid = t.paid_amount or 0
    return max(0, round(eff - paid, 2))


def _patient_total_debt(treatments: list[Treatment]) -> float:
    """Суммарный долг по списку позиций."""
    return sum(_treatment_debt(t) for t in treatments if t.price is not None)


@router.message(F.text == "💰 Финансы", flags={"tier": 2})
async def cmd_finance(
    message: Message,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Главное меню финансов (доступ по правам, данные врача)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await message.answer("Нет доступа к разделу «Финансы».")
        return
    doctor_id = effective_doctor.id
    stmt = select(
        func.coalesce(func.sum(Treatment.price), 0).label("total"),
        func.count(Treatment.id).label("count"),
    ).where(Treatment.doctor_id == doctor_id)
    result = await db_session.execute(stmt)
    row = result.first()
    total = float(row.total or 0)
    count = int(row.count or 0)

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="finance_stats")
    builder.button(text="💵 Оплаты", callback_data="finance_payments")
    builder.adjust(1)

    await message.answer(
        f"💰 **Финансовый модуль**\n\n"
        f"📈 Всего записей: {count}\n"
        f"💵 Общая сумма: {format_money(total)}\n\n"
        f"Выберите действие:",
        reply_markup=builder.as_markup(),
    )


# --- Статистика за период ---

@router.callback_query(F.data == "finance_stats", flags={"tier": 2})
async def finance_stats_menu(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Выбор периода для статистики (доступ по правам)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await callback.answer("Нет доступа к разделу «Финансы».", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Вся история", callback_data="finance_stats_all")
    builder.button(text="За 7 дней", callback_data="finance_stats_7")
    builder.button(text="За 30 дней", callback_data="finance_stats_30")
    builder.button(text="За 90 дней", callback_data="finance_stats_90")
    builder.button(text="Текущий месяц", callback_data="finance_stats_month")
    builder.button(text="⬅️ Назад", callback_data="finance_back")
    builder.adjust(1)
    await callback.message.edit_text(
        "📊 **Статистика**\n\n"
        "«Вся история» — все данные из базы (включая до обновления бота).\n\nВыберите период:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


def _period_range(period_key: str) -> tuple[datetime | None, datetime | None]:
    """Начало и конец периода. Для 'all' возвращает (None, None) — без фильтра по дате."""
    if period_key == "all":
        return None, None
    now = datetime.now()
    if period_key == "7":
        start = now - timedelta(days=7)
    elif period_key == "30":
        start = now - timedelta(days=30)
    elif period_key == "90":
        start = now - timedelta(days=90)
    elif period_key == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=30)
    return start, now


@router.callback_query(F.data.regexp(r"^finance_stats_(all|7|30|90|month)$"), flags={"tier": 2})
async def finance_stats_show(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Показать статистику за выбранный период (доступ по правам)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await callback.answer("Нет доступа к разделу «Финансы».", show_alert=True)
        return
    period_key = callback.data.replace("finance_stats_", "")
    start, end = _period_range(period_key)
    doctor_id = effective_doctor.id

    labels = {
        "all": "вся история",
        "7": "7 дней",
        "30": "30 дней",
        "90": "90 дней",
        "month": "текущий месяц",
    }
    period_label = labels.get(period_key, period_key)

    # Пациенты: за период или все (без фильтра по дате)
    if start is not None and end is not None:
        stmt_patients = select(func.count(func.distinct(Appointment.patient_id))).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.date_time >= start,
                Appointment.date_time <= end,
                Appointment.patient_id.isnot(None),
            )
        )
    else:
        stmt_patients = select(func.count(func.distinct(Appointment.patient_id))).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id.isnot(None),
            )
        )
    r = await db_session.execute(stmt_patients)
    patients_count = r.scalar() or 0

    # Лечения: за период или все
    if start is not None and end is not None:
        stmt_treatments = select(Treatment).where(
            and_(
                Treatment.doctor_id == doctor_id,
                Treatment.created_at >= start,
                Treatment.created_at <= end,
            )
        ).order_by(Treatment.created_at)
    else:
        stmt_treatments = select(Treatment).where(
            Treatment.doctor_id == doctor_id
        ).order_by(Treatment.created_at)
    res_t = await db_session.execute(stmt_treatments)
    treatments = list(res_t.scalars().all())

    # Популярные услуги (по service_name)
    service_counts: dict[str, int] = {}
    for t in treatments:
        name = (t.service_name or "Без названия").strip() or "Без названия"
        service_counts[name] = service_counts.get(name, 0) + 1
    popular = sorted(service_counts.items(), key=lambda x: -x[1])[:10]

    # Денежный учёт за период: оплачено / не оплачено (долг)
    total_paid = 0.0
    total_debt = 0.0
    total_sum = 0.0
    for t in treatments:
        if t.price is None:
            continue
        eff = treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        total_sum += eff
        paid = t.paid_amount or 0
        total_paid += paid
        debt = _treatment_debt(t)
        total_debt += debt

    if start is not None and end is not None:
        date_line = f"📅 {start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"
    else:
        date_line = "📅 Все записи в базе (включая данные до обновления)"
    lines = [
        f"📊 **Статистика: {period_label}**",
        date_line,
        "",
        f"👥 **Пациентов записалось:** {patients_count}",
        "",
        "**Популярные услуги:**",
    ]
    if popular:
        for name, cnt in popular:
            lines.append(f"• {name} — {cnt}")
    else:
        lines.append("— нет данных")
    lines.extend([
        "",
        "**Денежный учёт за период:**",
        f"💵 Сумма к оплате: {format_money(total_sum)}",
        f"✅ Оплачено: {format_money(total_paid)}",
        f"❌ Долг: {format_money(total_debt)}",
    ])

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Другой период", callback_data="finance_stats")
    builder.button(text="⬅️ В меню финансов", callback_data="finance_back")
    builder.adjust(1)
    await callback.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()


# --- Оплаты: список пациентов с индикатором долга ---

@router.callback_query(F.data == "finance_payments", flags={"tier": 2})
async def finance_payments_list(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Список пациентов с долгом (доступ по правам)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await callback.answer("Нет доступа к разделу «Финансы».", show_alert=True)
        return
    doctor_id = effective_doctor.id
    stmt = select(Patient).where(Patient.doctor_id == doctor_id).order_by(Patient.full_name)
    res = await db_session.execute(stmt)
    patients = list(res.scalars().all())
    if not patients:
        await callback.message.edit_text(
            "💵 **Оплаты**\n\nНет пациентов в базе. Добавьте пациентов в разделе «👥 Пациенты»."
        )
        await callback.answer()
        return

    stmt_t = select(Treatment).where(
        and_(Treatment.doctor_id == doctor_id)
    )
    res_t = await db_session.execute(stmt_t)
    all_treatments = list(res_t.scalars().all())
    by_patient: dict[int, list[Treatment]] = {}
    for t in all_treatments:
        by_patient.setdefault(t.patient_id, []).append(t)

    builder = InlineKeyboardBuilder()
    for p in patients:
        treatments = by_patient.get(p.id, [])
        debt = _patient_total_debt(treatments)
        if debt > 0:
            label = f"🔴 {p.full_name} — долг {format_money(debt)}"
        else:
            label = f"🟢 {p.full_name}"
        builder.button(text=label, callback_data=f"history_payment_{p.id}")
    builder.button(text="⬅️ Назад", callback_data="finance_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "💵 **Оплаты**\n\n"
        "🟢 — всё оплачено\n"
        "🔴 — есть долг\n\n"
        "Нажмите на пациента, чтобы внести оплату:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "finance_back", flags={"tier": 2})
async def finance_back(
    callback: CallbackQuery,
    effective_doctor: User,
    assistant_permissions: dict,
    db_session: AsyncSession,
):
    """Вернуться в главное меню финансов (доступ по правам)."""
    if not can_access(assistant_permissions, FEATURE_FINANCE):
        await callback.answer("Нет доступа к разделу «Финансы».", show_alert=True)
        return
    doctor_id = effective_doctor.id
    stmt = select(
        func.coalesce(func.sum(Treatment.price), 0).label("total"),
        func.count(Treatment.id).label("count"),
    ).where(Treatment.doctor_id == doctor_id)
    result = await db_session.execute(stmt)
    row = result.first()
    total = float(row.total or 0)
    count = int(row.count or 0)
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="finance_stats")
    builder.button(text="💵 Оплаты", callback_data="finance_payments")
    builder.adjust(1)
    await callback.message.edit_text(
        f"💰 **Финансовый модуль**\n\n"
        f"📈 Всего записей: {count}\n"
        f"💵 Общая сумма: {format_money(total)}\n\n"
        f"Выберите действие:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
