from decimal import Decimal as D

from cse_screening.units import detect_unit, normalize_monetary, parse_number


def test_unit_normalization_thousands():
    assert normalize_monetary(D("12.5"), "Rs. '000") == D("12500.0")


def test_unit_detection_millions():
    assert detect_unit("Amounts in LKR million") == ("LKR million", D(1000000))


def test_parentheses_are_negative():
    assert parse_number("(1,234.50)") == D("-1234.50")
