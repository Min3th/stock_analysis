from datetime import date
from decimal import Decimal as D

from cse_screening.pipeline import _deduplicate_history, _prior_year_end


def _row(period: str, value: str, source_period: str, basis: str = "reported current"):
    return {
        "Ticker": "TEST.N0000",
        "Metric": "revenue",
        "Financial Year End": period,
        "Value": D(value),
        "Source Period End": source_period,
        "Confidence": D("0.82"),
        "Value Basis": basis,
    }


def test_history_prefers_direct_current_year_value_over_later_comparative():
    rows = [
        _row("2025-03-31", "90", "2025-03-31"),
        _row("2025-03-31", "95", "2026-03-31", "reported comparative"),
    ]
    selected = _deduplicate_history(rows)
    assert len(selected) == 1
    assert selected[0]["Value"] == D(90)


def test_prior_year_end_preserves_non_march_fiscal_year_and_handles_leap_day():
    assert _prior_year_end(date(2026, 6, 30), 2) == date(2024, 6, 30)
    assert _prior_year_end(date(2024, 2, 29), 1) == date(2023, 2, 28)
