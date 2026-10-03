from datetime import date
from decimal import Decimal

from cse_screening.models import FinancialPeriod, PeriodKind
from cse_screening.periods import (
    period_label,
    periods_comparable,
    ttm_from_annual_and_ytd,
    ttm_from_quarters,
)


def test_period_matching_refuses_annual_and_interim_mix():
    annual = FinancialPeriod(
        end_date=date(2025, 3, 31), kind=PeriodKind.ANNUAL, months=12, label="FY25"
    )
    interim = FinancialPeriod(
        end_date=date(2026, 6, 30), kind=PeriodKind.INTERIM, months=3, label="Q1 FY27"
    )
    assert not periods_comparable(annual, interim)


def test_quarter_parser():
    assert period_label("2026Q3") == (2026, 3)


def test_ttm_from_annual_and_matching_ytd():
    assert ttm_from_annual_and_ytd(
        Decimal(100),
        Decimal(30),
        Decimal(20),
        annual_end=date(2026, 3, 31),
        current_end=date(2026, 6, 30),
        prior_end=date(2025, 6, 30),
        months=3,
    ) == Decimal(110)


def test_ttm_refuses_mismatched_comparative_period():
    assert (
        ttm_from_annual_and_ytd(
            Decimal(100),
            Decimal(30),
            Decimal(20),
            annual_end=date(2026, 3, 31),
            current_end=date(2026, 6, 30),
            prior_end=date(2025, 9, 30),
            months=3,
        )
        is None
    )


def test_ttm_from_four_consecutive_quarters():
    quarters = [
        (date(2025, 9, 30), Decimal(20), 3),
        (date(2025, 12, 31), Decimal(25), 3),
        (date(2026, 3, 31), Decimal(30), 3),
        (date(2026, 6, 30), Decimal(35), 3),
    ]
    assert ttm_from_quarters(quarters) == Decimal(110)
