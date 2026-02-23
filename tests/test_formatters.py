"""Тесты для app.utils.formatters."""
from app.utils.formatters import format_money, treatment_effective_price


class TestFormatMoney:
    def test_basic(self):
        result = format_money(1000)
        assert "сум" in result
        assert "1 000" in result

    def test_zero(self):
        result = format_money(0)
        assert "0" in result
        assert "сум" in result

    def test_large_number(self):
        result = format_money(1_500_000)
        assert "1 500 000" in result

    def test_with_decimals(self):
        result = format_money(1234.56, decimals=2)
        assert "сум" in result


class TestTreatmentEffectivePrice:
    def test_no_discount(self):
        assert treatment_effective_price(100000, None, None) == 100000

    def test_percent_discount(self):
        assert treatment_effective_price(100000, 10, None) == 90000

    def test_amount_discount(self):
        assert treatment_effective_price(100000, None, 20000) == 80000

    def test_both_discounts(self):
        # Сначала процент, потом сумма: 100000 * 0.9 - 10000 = 80000
        result = treatment_effective_price(100000, 10, 10000)
        assert result == 80000

    def test_none_price(self):
        assert treatment_effective_price(None, 10, 5000) == 0.0

    def test_discount_exceeds_price(self):
        # Не может быть отрицательным — max(0, ...)
        result = treatment_effective_price(10000, None, 50000)
        assert result == 0.0

    def test_100_percent_discount(self):
        result = treatment_effective_price(100000, 100, None)
        assert result == 0.0
