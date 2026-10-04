from datetime import date
from decimal import Decimal as D

from cse_screening.pipeline import (
    _add_growth_metrics,
    _deduplicate_history,
    _prior_year_end,
)


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


def test_growth_uses_chronological_deduplicated_three_year_series():
    rows = [
        _row("2024-03-31", "100", "2025-03-31", "reported comparative"),
        _row("2025-03-31", "120", "2025-03-31"),
        _row("2026-03-31", "144", "2026-03-31"),
        _row("2025-03-31", "110", "2025-03-31"),
    ]
    output = {}
    _add_growth_metrics(output, "TEST.N0000", rows)
    assert output["Revenue Growth YoY"] == D("0.2")
    assert output["3Y Revenue CAGR"] == D("0.2")


def test_cagr_rejects_nonconsecutive_fiscal_periods():
    rows = [
        _row("2023-03-31", "100", "2023-03-31"),
        _row("2025-03-31", "120", "2025-03-31"),
        _row("2026-03-31", "144", "2026-03-31"),
    ]
    output = {}
    _add_growth_metrics(output, "TEST.N0000", rows)
    assert output["3Y Revenue CAGR"] is None


def test_prior_year_end_preserves_non_march_fiscal_year_and_handles_leap_day():
    assert _prior_year_end(date(2026, 6, 30), 2) == date(2024, 6, 30)
    assert _prior_year_end(date(2024, 2, 29), 1) == date(2023, 2, 28)
