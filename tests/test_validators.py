"""Тесты для app.utils.validators."""
from app.utils.validators import (
    validate_phone,
    validate_date,
    validate_tooth_number,
    validate_price,
    validate_string_length,
    MAX_NAME_LENGTH,
    MAX_SERVICE_NAME_LENGTH,
)


class TestValidatePhone:
    def test_valid_international(self):
        assert validate_phone("+998901234567") is True

    def test_valid_digits_only(self):
        assert validate_phone("998901234567") is True

    def test_valid_with_formatting(self):
        assert validate_phone("+7 (999) 123-45-67") is True

    def test_empty(self):
        assert validate_phone("") is False

    def test_too_short(self):
        assert validate_phone("123") is False

    def test_letters_only(self):
        assert validate_phone("abcdefghij") is False


class TestValidateDate:
    def test_valid(self):
        assert validate_date("01.01.2024") is True

    def test_valid_end_of_year(self):
        assert validate_date("31.12.2025") is True

    def test_invalid_day(self):
        assert validate_date("32.01.2024") is False

    def test_wrong_format(self):
        assert validate_date("2024-01-01") is False

    def test_empty(self):
        assert validate_date("") is False


class TestValidateToothNumber:
    def test_valid_upper_left(self):
        assert validate_tooth_number("11") is True

    def test_valid_lower_right(self):
        assert validate_tooth_number("48") is True

    def test_valid_child_tooth(self):
        assert validate_tooth_number("51") is True

    def test_zero(self):
        assert validate_tooth_number("0") is False

    def test_out_of_range(self):
        assert validate_tooth_number("99") is False

    def test_empty(self):
        assert validate_tooth_number("") is False


class TestValidatePrice:
    def test_positive(self):
        assert validate_price("100") is True

    def test_zero(self):
        assert validate_price("0") is True

    def test_negative(self):
        assert validate_price("-1") is False

    def test_not_a_number(self):
        assert validate_price("abc") is False


class TestValidateStringLength:
    def test_within_bounds(self):
        assert validate_string_length("abc", 1, 255) is True

    def test_empty_fails_min_1(self):
        assert validate_string_length("", 1, 255) is False

    def test_exceeds_max(self):
        assert validate_string_length("a" * 256, 1, 255) is False

    def test_below_min(self):
        assert validate_string_length("ab", 3, 10) is False

    def test_exact_max(self):
        assert validate_string_length("a" * 100, 1, 100) is True

    def test_spaces_stripped(self):
        assert validate_string_length("  ab  ", 1, 2) is True


class TestMaxLengthConstants:
    def test_name_length(self):
        assert MAX_NAME_LENGTH == 100

    def test_service_name_length(self):
        assert MAX_SERVICE_NAME_LENGTH == 200
