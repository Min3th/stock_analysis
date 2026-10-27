import json
from decimal import Decimal
from pathlib import Path

import pytest

from cse_screening.calculations.screening import (
    NOT_APPLICABLE,
    Snapshot,
    build_snapshot,
    screening_metrics,
)
from cse_screening.extractors.primary import FINANCIAL_PROFILES
from cse_screening.extractors.statements import extract_document_metrics

FIXTURES = Path(__file__).parent / "fixtures" / "banks"


def _facts(name: str, profile: str | None = "bank") -> dict[str, dict]:
    fixture = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    facts = extract_document_metrics(fixture["pages"], "annual_report", profile)
    return {fact["metric"]: fact for fact in facts}


@pytest.mark.parametrize("name", ["seyb_annual.json", "ntb_annual.json"])
def test_bank_revenue_is_total_operating_income(name):
    facts = _facts(name)
    assert "Total Operating Income".casefold() in facts["revenue"]["source_text"].casefold()
    assert facts["revenue"]["value"] == facts["total_operating_income"]["value"]
    assert facts["revenue"]["extraction_method"] == "bank_total_operating_income"
    assert facts["net_interest_income"]["value"] < facts["revenue"]["value"]


def test_non_bank_profile_does_not_invent_bank_rows():
    facts = _facts("seyb_annual.json", profile=None)
    assert "total_operating_income" not in facts
    assert "net_interest_income" not in facts
    assert facts.get("revenue", {}).get("confidence", Decimal(0)) < Decimal("0.8")


@pytest.mark.parametrize("name", ["seyb_annual.json", "ntb_annual.json"])
def test_bank_balance_sheet_identity_holds(name):
    facts = _facts(name)
    assert (
        facts["total_assets"]["value"]
        == facts["total_liabilities"]["value"] + facts["total_equity"]["value"]
    )
    assert facts["loans_and_advances"]["value"] > 0
    assert facts["customer_deposits"]["value"] > 0
    assert facts["total_assets"]["value"] > facts["loans_and_advances"]["value"]


def test_bank_eps_agrees_with_attributable_profit():
    facts = _facts("ntb_annual.json")
    profit = (facts.get("net_profit_attributable") or facts["net_profit"])["value"]
    # Ordinary shares from the stated-capital note on another page of the report
    # (it is not part of the saved pages): 330,637,482 for Nations Trust Bank.
    shares = Decimal(330637482)
    assert float(facts["eps"]["value"] * shares) == pytest.approx(float(profit), rel=0.02)


def test_financial_ratios_are_not_applicable_not_missing():
    facts = list(_facts("ntb_annual.json").values())
    for fact in facts:
        fact["fact_id"] = f"NTB:{fact['metric']}"
        fact["period"] = "2025-12-31"
    document = {"kind": "annual_report", "period_end": "2025-12-31", "title": "AR"}
    snapshot = build_snapshot("NTB.N0000", [(document, facts)], lambda fact: True)
    assert isinstance(snapshot, Snapshot)
    values, rows = screening_metrics(snapshot, Decimal(100), [], "bank")
    for column in NOT_APPLICABLE:
        assert values[column] is None
        row = next(item for item in rows if item["Metric"] == column)
        assert row["Status"] == "not_applicable"
        assert row["Notes"].startswith("Not applicable:")
    assert values["Not Applicable Metrics"] == "; ".join(NOT_APPLICABLE)
    assert values["Revenue"] is not None
    plain, _ = screening_metrics(snapshot, Decimal(100), [], None)
    assert plain["Not Applicable Metrics"] is None if "Not Applicable Metrics" in plain else True


def test_profiles_cover_the_financial_industry_groups():
    assert FINANCIAL_PROFILES == {
        "Banks": "bank",
        "Diversified Financials": "bank",
        "Insurance": "insurer",
    }
