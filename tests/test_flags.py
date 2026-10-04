from decimal import Decimal as D

from cse_screening.validators.flags import (
    company_flags,
    consecutive_decline,
    sector_relative_flags,
)


def _history(metric: str, values: list[str]) -> list[dict]:
    return [
        {
            "Ticker": "TEST.N0000",
            "Metric": metric,
            "Financial Year End": f"{year}-03-31",
            "Value": D(value),
        }
        for year, value in zip((2026, 2025, 2024), values, strict=True)
    ]


def test_consecutive_decline_requires_three_matching_annual_periods():
    assert consecutive_decline(_history("eps", ["1", "2", "3"]), "TEST.N0000", "eps")
    assert not consecutive_decline(_history("eps", ["2", "1", "3"]), "TEST.N0000", "eps")


def test_company_flags_cover_required_absolute_anomalies():
    row = {
        "Ticker": "TEST.N0000",
        "EPS": D(-1),
        "Net Profit": D(100),
        "Operating Cash Flow": D(-10),
        "OCF / Net Profit": D("-0.1"),
        "Debt-to-Equity": D(3),
        "Payout Ratio": D("1.2"),
        "Recent Volume": D(100),
    }
    history = [*_history("eps", ["1", "2", "3"]), *_history("revenue", ["4", "5", "6"])]
    flags = company_flags(
        row,
        {"low_liquidity_daily_volume": 10000},
        history=history,
        total_equity=D(-5),
        one_off_evidence=[{"page": 1}],
    )
    assert set(flags) == {
        "negative EPS",
        "declining EPS for 2+ consecutive years",
        "declining revenue for 2+ consecutive years",
        "negative operating cash flow",
        "operating cash flow materially below net profit",
        "high debt-to-equity",
        "negative equity",
        "dividend payout above 100%",
        "low trading liquidity (current-volume snapshot)",
        "possible one-off profit or loss",
    }


def test_sector_relative_valuation_flags_use_positive_medians():
    rows = [
        {"Ticker": "A", "P/E": D(10), "P/B": D(1)},
        {"Ticker": "B", "P/E": D(12), "P/B": D("1.2")},
        {"Ticker": "HIGH", "P/E": D(50), "P/B": D(4)},
        {"Ticker": "LOW", "P/E": D(8), "P/B": D("0.2")},
        {"Ticker": "NEG", "P/E": D(-20), "P/B": D(-1)},
    ]
    flags = sector_relative_flags(rows, {})
    assert flags["HIGH"] == [
        "P/E unusually high relative to sector median",
        "P/B unusually high relative to sector median",
    ]
    assert flags["LOW"] == ["P/B unusually low relative to sector median"]
    assert flags["NEG"] == []
