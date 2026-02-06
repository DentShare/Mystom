"""Сервис услуг по категориям"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import Service

# Категории услуг
CATEGORIES = {
    "therapy": ("Терапия", "🦷"),
    "orthopedics": ("Ортопедия", "🦴"),
    "surgery": ("Хирургия", "🔪"),
    "orthodontics": ("Ортодонтия", "😁"),
    "endodontics": ("Эндодонтия", "🦷"),
}

# Услуги по умолчанию (цены в узбекских сумах)
DEFAULT_SERVICES = {
    "therapy": [
        ("Консультация", 200_000),
        ("Лечение кариеса", 450_000),
        ("Профессиональная гигиена", 600_000),
        ("Отбеливание", 1_500_000),
    ],
    "orthopedics": [
        ("Консультация ортопеда", 250_000),
        ("Съемный протез", 2_000_000),
        ("Коронка металлокерамика", 1_500_000),
        ("Имплант с коронкой", 6_000_000),
    ],
    "surgery": [
        ("Удаление зуба простое", 350_000),
        ("Удаление зуба сложное", 650_000),
        ("Имплантация", 4_500_000),
        ("Синус-лифтинг", 3_500_000),
    ],
    "orthodontics": [
        ("Консультация ортодонта", 350_000),
        ("Брекет-система", 10_000_000),
        ("Элайнеры", 15_000_000),
        ("Ретейнер", 2_000_000),
    ],
    "endodontics": [
        ("Лечение каналов 1 канал", 450_000),
        ("Лечение каналов 2 канала", 700_000),
        ("Лечение каналов 3 канала", 1_000_000),
        ("Перелечивание каналов", 1_000_000),
    ],
}


async def get_categories() -> List[tuple[str, str, str]]:
    """Список категорий: (id, название, emoji)"""
    return [(cat_id, name, emoji) for cat_id, (name, emoji) in CATEGORIES.items()]


async def get_services_by_category(
    db_session: AsyncSession,
    doctor_id: int,
    category: str
) -> List[Service]:
    """Услуги врача по категории"""
    stmt = (
        select(Service)
        .where(
            and_(
                Service.doctor_id == doctor_id,
                Service.category == category
            )
        )
        .order_by(Service.sort_order, Service.name)
    )
    result = await db_session.execute(stmt)
    return list(result.scalars().all())


async def ensure_default_services(db_session: AsyncSession, doctor_id: int) -> None:
    """Создать услуги по умолчанию: для каждой категории, где у врача ещё нет услуг."""
    for category, default_list in DEFAULT_SERVICES.items():
        stmt = (
            select(Service)
            .where(
                and_(
                    Service.doctor_id == doctor_id,
                    Service.category == category
                )
            )
            .limit(1)
        )
        result = await db_session.execute(stmt)
        if result.scalar_one_or_none():
            continue  # В этой категории уже есть услуги

        for i, (name, price) in enumerate(default_list):
            service = Service(
                doctor_id=doctor_id,
                category=category,
                name=name,
                price=price,
                duration_minutes=30,
                sort_order=i,
            )
            db_session.add(service)
    await db_session.commit()


async def get_service_by_id(
    db_session: AsyncSession,
    service_id: int,
    doctor_id: int
) -> Service | None:
    """Получить услугу по ID"""
    stmt = select(Service).where(
        and_(
            Service.id == service_id,
            Service.doctor_id == doctor_id
        )
    )
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()
