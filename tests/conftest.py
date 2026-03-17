"""Общие фикстуры для тестов."""
import pytest
import pytest_asyncio
from datetime import datetime, date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database.models import Base, User, Patient, Appointment, Service
from app.utils.permissions import (
    full_permissions, default_permissions,
    FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
    FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
    FEATURE_EXPORT, FEATURE_SETTINGS,
    LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT,
)


# --- Async DB fixtures (SQLite in-memory) ---

@pytest_asyncio.fixture
async def db_engine():
    """Async SQLite engine для тестов."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Async session для тестов."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def doctor(db_session: AsyncSession):
    """Создаёт врача-пользователя для тестов."""
    user = User(
        telegram_id=111111,
        full_name="Доктор Тестов",
        specialization="Терапевт",
        subscription_tier=1,
        role="owner",
        registration_completed=True,
        timezone="Asia/Tashkent",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def patient(db_session: AsyncSession, doctor: User):
    """Создаёт пациента для тестов."""
    p = Patient(
        doctor_id=doctor.id,
        full_name="Иванов Иван Иванович",
        phone="+998901234567",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def appointment(db_session: AsyncSession, doctor: User, patient: Patient):
    """Создаёт запись на приём для тестов."""
    apt = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        date_time=datetime(2026, 3, 17, 14, 0),
        duration_minutes=30,
        service_description="Консультация",
        status="planned",
    )
    db_session.add(apt)
    await db_session.commit()
    await db_session.refresh(apt)
    return apt


@pytest.fixture
def owner_permissions():
    """Полные права (врач/владелец)."""
    return full_permissions()


@pytest.fixture
def default_assistant_permissions():
    """Права ассистента по умолчанию."""
    return default_permissions()


@pytest.fixture
def view_only_permissions():
    """Все разделы — только просмотр."""
    return {f: LEVEL_VIEW for f in [
        FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
        FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
        FEATURE_EXPORT, FEATURE_SETTINGS,
    ]}


@pytest.fixture
def no_permissions():
    """Нет доступа ни к чему."""
    return {f: LEVEL_NONE for f in [
        FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
        FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
        FEATURE_EXPORT, FEATURE_SETTINGS,
    ]}
