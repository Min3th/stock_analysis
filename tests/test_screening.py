from decimal import Decimal as D

from cse_screening.calculations.screening import (
    NOT_MEANINGFUL,
    SCREEN_COLUMNS,
    build_snapshot,
    screening_metrics,
)
from cse_screening.validators.flags import consecutive_decline

REQUIRED_ORDER = [
    "Ticker",
    "Company",
    "Current Price",
    "Market Cap",
    "Revenue",
    "Revenue Growth YoY",
    "Net Profit",
    "EPS",
    "EPS Growth YoY",
    "3Y Revenue CAGR",
    "3Y EPS CAGR",
    "ROE",
    "ROA",
    "Debt-to-Equity",
    "Net Debt",
    "Operating Cash Flow",
    "Free Cash Flow",
    "OCF / Net Profit",
    "P/E",
    "P/B",
    "DPS",
    "Dividend Yield",
    "Payout Ratio",
    "Earnings Yield",
    "Latest Financial Period",
    "Data Confidence",
    "Flags",
]


def fact(metric, value, previous=None, *, months=None, confidence="0.9", page=1):
    return {
        "metric": metric,
        "value": D(str(value)),
        "previous_value": None if previous is None else D(str(previous)),
        "confidence": D(confidence),
        "page": page,
        "fact_id": f"T:{metric}:{value}",
        "period_months": months,
    }


ANNUAL = {"kind": "annual_report", "period_end": "2026-03-31", "title": "AR 2025/26"}
INTERIM = {
    "kind": "interim_statement",
    "period_end": "2026-06-30",
    "title": "Q1",
    "period_months": 3,
    "comparative_period_end": "2025-06-30",
}


def annual_facts(**overrides):
    values = {
        "revenue": fact("revenue", 1000, 800),
        "net_profit": fact("net_profit", 100, 80),
        "net_profit_attributable": fact("net_profit_attributable", 90, 72),
        "eps": fact("eps", 9, "7.2"),
        "dps": fact("dps", 3, 2),
        "total_assets": fact("total_assets", 2000, 1800),
        "total_equity": fact("total_equity", 1100, 1000),
        "ordinary_equity": fact("ordinary_equity", 1000, 900),
        "total_debt": fact("total_debt", 400, 350),
        "cash": fact("cash", 150, 100),
        "operating_cash_flow": fact("operating_cash_flow", 120, 90),
        "capital_expenditure": fact("capital_expenditure", -50, -40),
        "ordinary_shares_outstanding": fact("ordinary_shares_outstanding", 10),
    }
    values.update(overrides)
    return [item for item in values.values() if item is not None]


def interim_facts(months=3):
    return [
        fact("revenue", 300, 250, months=months),
        fact("net_profit", 30, 20, months=months),
        fact("net_profit_attributable", 27, 18, months=months),
        fact("eps", "2.7", "1.8", months=months),
        fact("operating_cash_flow", 10, 40, months=months),
        fact("capital_expenditure", -20, -10, months=months),
    ]


def ratio(rows, metric):
    return next(item for item in rows if item["Metric"] == metric)


def test_required_screening_columns_lead_in_specification_order():
    assert SCREEN_COLUMNS[: len(REQUIRED_ORDER)] == REQUIRED_ORDER
    assert "Net Profit Growth YoY" in SCREEN_COLUMNS


def test_ttm_is_used_when_the_interim_period_is_confirmed():
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (INTERIM, interim_facts())])
    values, rows = screening_metrics(snapshot, D(90), [])
    assert values["Revenue"] == D(1050)
    assert values["EPS"] == D("9.9")
    assert values["Income Period Basis"] == "TTM to 2026-06-30"
    assert values["P/E"] == D(90) / D("9.9")
    assert ratio(rows, "P/E")["Period Basis"] == "TTM to 2026-06-30"
    lineage = ratio(rows, "revenue (TTM)")
    assert (lineage["Numerator"], lineage["Current YTD"], lineage["Prior YTD"]) == (
        D(1000),
        D(300),
        D(250),
    )


def test_bare_interim_values_never_reach_the_screening_row():
    unconfirmed = [dict(item, period_months=None) for item in interim_facts()]
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (INTERIM, unconfirmed)])
    values, _rows = screening_metrics(snapshot, D(90), [])
    assert values["Revenue"] == D(1000)
    assert values["EPS"] == D(9)
    assert values["Income Period Basis"] == "FY to 2026-03-31"
    assert values["Latest Financial Period"] == "FY to 2026-03-31"
    assert any("not confirmed" in note for note in snapshot.notes)


def test_quarter_only_columns_do_not_build_a_six_month_ttm():
    half_year = dict(INTERIM, period_end="2026-09-30", period_months=6)
    half_year["comparative_period_end"] = "2025-09-30"
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (half_year, interim_facts(3))])
    assert snapshot.ttm == {}
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (half_year, interim_facts(6))])
    assert snapshot.ttm["revenue"]["value"] == D(1050)


def test_year_to_date_out_of_proportion_to_the_year_is_rejected():
    wrong_unit = interim_facts()
    wrong_unit[0] = fact("revenue", "0.3", "0.25", months=3)
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (INTERIM, wrong_unit)])
    assert "revenue" not in snapshot.ttm
    assert snapshot.income_basis == "fy"


def test_older_annual_report_does_not_fill_a_gap_in_the_latest_one():
    older = dict(ANNUAL, period_end="2025-03-31", title="AR 2024/25")
    latest = annual_facts(total_debt=None)
    snapshot = build_snapshot("T", [(older, annual_facts()), (ANNUAL, latest)])
    values, _ = screening_metrics(snapshot, D(90), [])
    assert values["Debt-to-Equity"] is None and values["Net Debt"] is None


def test_same_period_inputs_for_payout_and_cash_conversion():
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts()), (INTERIM, interim_facts())])
    values, rows = screening_metrics(snapshot, D(90), [])
    assert values["Payout Ratio"] == D(3) / D(9)
    assert ratio(rows, "Payout Ratio")["Period Basis"] == "FY to 2026-03-31"
    assert values["Operating Cash Flow"] == D(90)
    assert values["Free Cash Flow"] == D(90) - D(60)
    assert values["OCF / Net Profit"] == D(90) / D(110)
    assert values["Dividend Yield"] == D(3) / D(90)


def test_roe_uses_attributable_profit_and_average_parent_equity_with_inputs():
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts())])
    values, rows = screening_metrics(snapshot, D(90), [])
    assert values["ROE"] == D(90) / D(950)
    row = ratio(rows, "ROE")
    assert (row["Numerator"], row["Denominator"]) == (D(90), D(950))
    assert "T:net_profit_attributable:90" in row["Input Fact IDs"]
    assert values["Book Value Per Share"] == D(100)
    assert values["P/B"] == D("0.9")


def test_growth_compares_columns_of_the_latest_statement_and_records_inputs():
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts())])
    values, rows = screening_metrics(snapshot, D(90), [])
    assert values["Revenue Growth YoY"] == D("0.25")
    assert values["Net Profit Growth YoY"] == D("0.25")
    assert values["EPS Growth YoY"] == D("0.25")
    row = ratio(rows, "EPS Growth YoY")
    assert (row["Numerator"], row["Denominator"]) == (D(9), D("7.2"))


def _history(metric, rows):
    return [
        {
            "Ticker": "T",
            "Metric": metric,
            "Financial Year End": year,
            "Source Period End": source,
            "Value": D(str(value)),
            "Value Basis": "reported current" if year == source else "reported comparative",
            "Source Document": f"AR {source}",
            "Source Page": 5,
        }
        for year, source, value in rows
    ]


def test_cagr_follows_one_basis_through_adjacent_reports():
    history = _history(
        "revenue",
        [
            ("2026-03-31", "2026-03-31", 1000),
            ("2025-03-31", "2026-03-31", 800),
            ("2025-03-31", "2025-03-31", 800),
            ("2024-03-31", "2025-03-31", 640),
        ],
    )
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts())])
    values, rows = screening_metrics(snapshot, D(90), history)
    assert values["3Y Revenue CAGR"] == D("0.25")
    assert ratio(rows, "3Y Revenue CAGR")["Denominator"] == D(640)


def test_eps_cagr_is_withheld_after_a_share_split():
    history = _history(
        "eps",
        [
            ("2026-03-31", "2026-03-31", 9),
            ("2025-03-31", "2026-03-31", "7.2"),
            ("2025-03-31", "2025-03-31", "21.6"),
            ("2024-03-31", "2025-03-31", 18),
        ],
    )
    snapshot = build_snapshot("T", [(ANNUAL, annual_facts())])
    values, rows = screening_metrics(snapshot, D(90), history)
    assert values["3Y EPS CAGR"] is None
    assert "restated" in ratio(rows, "3Y EPS CAGR")["Notes"]
    assert values["EPS Growth YoY"] == D("0.25")


def test_negative_values_are_kept_but_ratios_on_a_negative_base_are_withheld():
    facts = annual_facts(
        eps=fact("eps", -4, -2),
        net_profit=fact("net_profit", -40, -20),
        net_profit_attributable=fact("net_profit_attributable", -40, -20),
        ordinary_equity=fact("ordinary_equity", -500, -450),
        total_equity=fact("total_equity", -500, -450),
    )
    snapshot = build_snapshot("T", [(ANNUAL, facts)])
    values, rows = screening_metrics(snapshot, D(20), [])
    assert values["EPS"] == D(-4)
    assert values["Net Profit"] == D(-40)
    assert values["Earnings Yield"] == D("-0.2")
    assert values["P/E"] is None and values["ROE"] is None
    assert values["Debt-to-Equity"] is None and values["Payout Ratio"] is None
    assert ratio(rows, "P/E")["Notes"] == NOT_MEANINGFUL
    assert ratio(rows, "P/E")["Denominator"] == D(-4)


def test_fifteen_month_year_is_labelled_and_not_compared_with_twelve_months():
    facts = annual_facts(
        revenue=fact("revenue", 1000, 800, months=15), eps=fact("eps", 9, "7.2", months=15)
    )
    snapshot = build_snapshot("T", [(ANNUAL, facts), (INTERIM, interim_facts())])
    values, _ = screening_metrics(snapshot, D(90), [])
    assert values["Income Period Basis"] == "15 months to 2026-03-31"
    assert values["Revenue Growth YoY"] is None and values["ROE"] is None
    assert snapshot.ttm == {}


def test_decline_flag_compares_within_each_report():
    split = _history(
        "eps",
        [
            ("2026-03-31", "2026-03-31", 9),
            ("2025-03-31", "2026-03-31", "7.2"),
            ("2025-03-31", "2025-03-31", "21.6"),
            ("2024-03-31", "2025-03-31", 25),
        ],
    )
    assert not consecutive_decline(split, "T", "eps")
    falling = _history(
        "eps",
        [
            ("2026-03-31", "2026-03-31", 5),
            ("2025-03-31", "2026-03-31", "7.2"),
            ("2025-03-31", "2025-03-31", "21.6"),
            ("2024-03-31", "2025-03-31", 25),
        ],
    )
    assert consecutive_decline(falling, "T", "eps")
