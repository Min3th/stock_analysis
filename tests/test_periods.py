from datetime import date

from cse_screening.models import FinancialPeriod, PeriodKind
from cse_screening.periods import period_label, periods_comparable


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
