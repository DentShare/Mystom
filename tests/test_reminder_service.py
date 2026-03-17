"""Тесты reminder_service."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services.reminder_service import get_reminder_minutes, format_reminder_message
from app.database.models import User, Appointment, Patient


class TestGetReminderMinutes:

    def _make_user(self, settings=None):
        u = MagicMock(spec=User)
        u.settings = settings
        return u

    def test_default(self):
        assert get_reminder_minutes(self._make_user()) == 30

    def test_none_settings(self):
        assert get_reminder_minutes(self._make_user(None)) == 30

    def test_custom_value(self):
        assert get_reminder_minutes(self._make_user({"reminder_minutes": 15})) == 15

    def test_min_clamp(self):
        """Значение < 5 зажимается до 5."""
        assert get_reminder_minutes(self._make_user({"reminder_minutes": 1})) == 5

    def test_max_clamp(self):
        """Значение > 1440 зажимается до 1440."""
        assert get_reminder_minutes(self._make_user({"reminder_minutes": 9999})) == 1440

    def test_invalid_value(self):
        assert get_reminder_minutes(self._make_user({"reminder_minutes": "abc"})) == 30

    def test_missing_key(self):
        assert get_reminder_minutes(self._make_user({"other": 10})) == 30


class TestFormatReminderMessage:

    def _make_appointment(self, patient_name=None, service_desc=None):
        apt = MagicMock(spec=Appointment)
        apt.date_time = datetime(2026, 3, 17, 14, 30)

        if patient_name:
            p = MagicMock(spec=Patient)
            p.full_name = patient_name
            apt.patient = p
        else:
            apt.patient = None

        apt.service_description = service_desc
        apt.service = None
        return apt

    def test_with_patient(self):
        msg = format_reminder_message(self._make_appointment(patient_name="Иванов И.И."), 30)
        assert "Иванов И.И." in msg
        assert "30" in msg
        assert "14:30" in msg
        assert "17.03.2026" in msg

    def test_without_patient(self):
        msg = format_reminder_message(self._make_appointment(), 15)
        assert "Пациент" in msg
        assert "15" in msg

    def test_with_service_description(self):
        msg = format_reminder_message(self._make_appointment(service_desc="Пломба"), 30)
        assert "Пломба" in msg
