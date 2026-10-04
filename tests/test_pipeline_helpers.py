from datetime import date
from decimal import Decimal as D

from cse_screening.calculations.screening import build_snapshot
from cse_screening.pipeline import _data_confidence, _history_rows, _market_share_count

ANNUAL = {"kind": "annual_report", "period_end": "2026-03-31", "title": "AR", "url": "u"}
ISSUER = {"ticker": "T.N0000", "name": "T PLC", "market_data": {"market_source_url": "cse"}}


def fact(metric, value, confidence="0.9", **extra):
    return {
        "metric": metric,
        "value": D(str(value)),
        "confidence": D(confidence),
        "page": 3,
        "fact_id": f"T:{metric}",
        "unit": "LKR",
        **extra,
    }


def usable(item):
    return item["confidence"] >= D("0.8")


def test_market_share_count_fills_in_only_when_no_reported_count_is_usable():
    facts = [fact("ordinary_shares_outstanding", 60, "0.60")]
    added = _market_share_count(ISSUER, [(ANNUAL, facts)], "2026-03-31", D(2000), False, usable)
    assert added["value"] == D(2000)
    assert added["extraction_method"] == "cse_market_data_implied_share_count"
    assert facts[-1] is added

    reported = [fact("ordinary_shares_outstanding", 1990)]
    assert (
        _market_share_count(ISSUER, [(ANNUAL, reported)], "2026-03-31", D(2000), False, usable)
        is None
    )


def test_market_share_count_is_not_used_for_a_dual_class_issuer():
    assert _market_share_count(ISSUER, [(ANNUAL, [])], "2026-03-31", D(2000), True, usable) is None


def test_data_confidence_reflects_core_metrics_of_the_latest_annual_report():
    core = ["revenue", "net_profit", "eps", "total_assets", "total_equity", "operating_cash_flow"]
    facts = [fact(metric, 10) for metric in core]
    documents = [(ANNUAL, facts)]
    snapshot = build_snapshot("T", documents, usable)
    assert _data_confidence(snapshot, documents, D("0.8")) == "high"

    facts[0]["confidence"] = D("0.62")
    snapshot = build_snapshot("T", documents, usable)
    assert _data_confidence(snapshot, documents, D("0.8")) == "review"

    for item in facts[:4]:
        item["confidence"] = D("0.62")
    snapshot = build_snapshot("T", documents, usable)
    assert _data_confidence(snapshot, documents, D("0.8")) == "low"


def test_history_keeps_current_and_comparative_but_not_a_fifteen_month_year():
    document = dict(ANNUAL, period_end=date(2026, 3, 31))
    revenue = fact("revenue", 1000, previous_value=D(800))
    rows = _history_rows(ISSUER, document, revenue, D("0.8"))
    assert [(row["Financial Year End"], row["Value"]) for row in rows] == [
        ("2026-03-31", D(1000)),
        ("2025-03-31", D(800)),
    ]
    assert _history_rows(ISSUER, document, dict(revenue, period_months=15), D("0.8")) == []
    assert _history_rows(ISSUER, document, dict(revenue, confidence=D("0.7")), D("0.8")) == []
