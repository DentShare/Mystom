"""Тесты хендлеров пациентов с реальной БД."""
import pytest
import pytest_asyncio
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import User, Patient
from app.handlers.patients import (
    cmd_patients,
    start_add_patient,
    process_patient_full_name,
    process_patient_phone,
)
from app.services.patient_service import search_patients, get_all_patients
from app.utils.permissions import full_permissions, LEVEL_NONE, LEVEL_VIEW, FEATURE_PATIENTS
from tests.helpers import make_message, make_callback, make_state


class TestPatientService:
    """Тесты сервисного слоя пациентов."""

    @pytest.mark.asyncio
    async def test_search_by_name(self, db_session: AsyncSession, doctor: User, patient: Patient):
        results = await search_patients(db_session, doctor.id, "Иванов")
        assert len(results) >= 1
        assert results[0].full_name == patient.full_name

    @pytest.mark.asyncio
    async def test_search_by_phone(self, db_session: AsyncSession, doctor: User, patient: Patient):
        results = await search_patients(db_session, doctor.id, "998901")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session: AsyncSession, doctor: User):
        results = await search_patients(db_session, doctor.id, "Несуществующий")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_other_doctor(self, db_session: AsyncSession, doctor: User, patient: Patient):
        """Пациенты другого врача не видны."""
        other = User(telegram_id=333333, full_name="Другой", role="owner", registration_completed=True)
        db_session.add(other)
        await db_session.commit()
        results = await search_patients(db_session, other.id, "Иванов")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_all_patients(self, db_session: AsyncSession, doctor: User, patient: Patient):
        results = await get_all_patients(db_session, doctor.id)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_create_patient(self, db_session: AsyncSession, doctor: User):
        """Создание пациента через БД."""
        p = Patient(doctor_id=doctor.id, full_name="Новый Пациент", phone="+998900000000")
        db_session.add(p)
        await db_session.commit()
        result = await search_patients(db_session, doctor.id, "Новый")
        assert len(result) == 1
        assert result[0].full_name == "Новый Пациент"


class TestPatientsHandler:
    """Тесты хендлера «Пациенты»."""

    @pytest.mark.asyncio
    async def test_no_access(self, db_session: AsyncSession, doctor: User):
        """Нет доступа → сообщение."""
        msg = make_message("👥 Пациенты")
        perms = {FEATURE_PATIENTS: LEVEL_NONE}
        await cmd_patients(msg, doctor, doctor, perms, db_session)
        msg.answer.assert_called_once()
        assert "доступ" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_shows_menu(self, db_session: AsyncSession, doctor: User):
        """С доступом — показывает меню с кнопками."""
        msg = make_message("👥 Пациенты")
        await cmd_patients(msg, doctor, doctor, full_permissions(), db_session)
        msg.answer.assert_called_once()
        assert msg.answer.call_args[1].get("reply_markup") is not None
        text = msg.answer.call_args[0][0]
        assert "пациент" in text.lower()


class TestAddPatientFlow:
    """Тесты флоу добавления пациента."""

    @pytest.mark.asyncio
    async def test_start_add_no_edit_permission(self):
        """Нет права на редактирование — отказ."""
        cb = make_callback("patient_add")
        perms = {FEATURE_PATIENTS: LEVEL_VIEW}
        await start_add_patient(cb, perms, make_state())
        cb.answer.assert_called_once()
        assert "прав" in cb.answer.call_args[1].get("text", cb.answer.call_args[0][0] if cb.answer.call_args[0] else "").lower() or cb.answer.call_args[1].get("show_alert", False)

    @pytest.mark.asyncio
    async def test_start_add_success(self):
        """Есть права — запрашивает ФИО."""
        cb = make_callback("patient_add")
        state = make_state()
        await start_add_patient(cb, full_permissions(), state)
        cb.message.edit_text.assert_called_once()
        assert "фио" in cb.message.edit_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_name_too_short(self):
        """ФИО < 3 символов — ошибка."""
        msg = make_message("Аб")
        state = make_state()
        await process_patient_full_name(msg, state)
        msg.answer.assert_called_once()
        assert "минимум" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_name_valid(self):
        """Корректное ФИО — сохраняется в state."""
        msg = make_message("Петров Пётр Петрович")
        state = make_state()
        await process_patient_full_name(msg, state)
        data = await state.get_data()
        assert data.get("full_name") == "Петров Пётр Петрович"
        msg.answer.assert_called_once()
        assert "телефон" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_phone_skip(self, db_session: AsyncSession, doctor: User):
        """Пропуск телефона (/skip) — пациент создаётся без телефона."""
        msg = make_message("/skip")
        state = make_state()
        await state.update_data(full_name="Тестов Тест")
        await process_patient_phone(msg, doctor, state, db_session)
        # Пациент создан с phone=None
        stmt = select(Patient).where(Patient.doctor_id == doctor.id, Patient.full_name == "Тестов Тест")
        result = await db_session.execute(stmt)
        p = result.scalar_one_or_none()
        assert p is not None
        assert p.phone is None

    @pytest.mark.asyncio
    async def test_process_phone_creates_patient(self, db_session: AsyncSession, doctor: User):
        """Ввод телефона — пациент создаётся в БД."""
        msg = make_message("+998901111111")
        state = make_state()
        await state.update_data(full_name="Сидоров Сидор")
        await process_patient_phone(msg, doctor, state, db_session)

        # Проверяем что пациент создан
        stmt = select(Patient).where(Patient.doctor_id == doctor.id, Patient.full_name == "Сидоров Сидор")
        result = await db_session.execute(stmt)
        p = result.scalar_one_or_none()
        assert p is not None
        assert p.phone == "+998901111111"

    @pytest.mark.asyncio
    async def test_process_phone_invalid(self, db_session: AsyncSession, doctor: User):
        """Некорректный телефон — ошибка валидации."""
        msg = make_message("123")
        state = make_state()
        await state.update_data(full_name="Тестов")
        await process_patient_phone(msg, doctor, state, db_session)
        msg.answer.assert_called_once()
        assert "некорректный" in msg.answer.call_args[0][0].lower()
