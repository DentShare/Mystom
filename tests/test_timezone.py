"""Тесты сервиса часовых поясов."""
from datetime import datetime

from app.services.timezone import local_to_utc, get_timezone_by_name, get_common_timezones


class TestLocalToUtc:

    def test_tashkent_to_utc(self):
        """Ташкент UTC+5: 15:00 local → 10:00 UTC."""
        local = datetime(2026, 3, 17, 15, 0)
        utc = local_to_utc(local, "Asia/Tashkent")
        assert utc == datetime(2026, 3, 17, 10, 0)

    def test_moscow_to_utc(self):
        """Москва UTC+3: 12:00 local → 09:00 UTC."""
        local = datetime(2026, 1, 15, 12, 0)
        utc = local_to_utc(local, "Europe/Moscow")
        assert utc == datetime(2026, 1, 15, 9, 0)

    def test_none_timezone_returns_unchanged(self):
        local = datetime(2026, 3, 17, 15, 0)
        assert local_to_utc(local, None) == local

    def test_empty_timezone_returns_unchanged(self):
        local = datetime(2026, 3, 17, 15, 0)
        assert local_to_utc(local, "") == local

    def test_unknown_timezone_returns_unchanged(self):
        local = datetime(2026, 3, 17, 15, 0)
        assert local_to_utc(local, "Invalid/Zone") == local

    def test_none_datetime_returns_none(self):
        assert local_to_utc(None, "Asia/Tashkent") is None

    def test_midnight_crossing(self):
        """Конверсия через полночь: Vladivostok UTC+10, 02:00 local → 16:00 UTC предыдущего дня."""
        local = datetime(2026, 3, 17, 2, 0)
        utc = local_to_utc(local, "Asia/Vladivostok")
        assert utc == datetime(2026, 3, 16, 16, 0)


class TestGetTimezoneByName:

    def test_valid_timezone(self):
        tz = get_timezone_by_name("Asia/Tashkent")
        assert tz is not None
        assert "Tashkent" in str(tz)

    def test_invalid_timezone(self):
        assert get_timezone_by_name("Not/A/Zone") is None


class TestGetCommonTimezones:

    def test_returns_list(self):
        zones = get_common_timezones()
        assert len(zones) > 0
        # Каждый элемент — кортеж (name, label)
        for name, label in zones:
            assert isinstance(name, str)
            assert isinstance(label, str)

    def test_tashkent_included(self):
        zones = get_common_timezones()
        names = [name for name, _ in zones]
        assert "Asia/Tashkent" in names
