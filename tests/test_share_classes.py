import json
from decimal import Decimal
from pathlib import Path

import pytest

from cse_screening.extractors.statements import extract_document_metrics, extract_share_classes

FIXTURE = Path(__file__).parent / "fixtures" / "share_classes" / "rhl_stated_capital.json"


def _pages() -> list[str]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["pages"]


def test_voting_and_non_voting_counts_come_from_the_stated_capital_note():
    facts = {fact["metric"]: fact for fact in extract_share_classes(_pages())}
    assert facts["ordinary_shares_voting"]["value"] == Decimal(165488271)
    assert facts["ordinary_shares_non_voting"]["value"] == Decimal(24201719)
    assert facts["ordinary_shares_outstanding"]["value"] == Decimal(189689990)
    assert facts["ordinary_shares_outstanding"]["confidence"] == Decimal("0.90")
    assert facts["ordinary_shares_voting"]["previous_value"] == Decimal(165488271)


def test_total_replaces_a_single_class_count_in_document_metrics():
    facts = {fact["metric"]: fact for fact in extract_document_metrics(_pages(), "annual_report")}
    assert facts["ordinary_shares_outstanding"]["value"] == Decimal(189689990)
    assert (
        facts["ordinary_shares_outstanding"]["extraction_method"] == "stated_capital_share_classes"
    )


def test_unconfirmed_sum_is_below_the_confidence_threshold():
    text = (
        "NOTE 5 - STATED CAPITAL\n"
        "Voting Shares 1,000,000 1,000,000\n"
        "Non Voting Shares 500,000 500,000\n"
    )
    facts = {fact["metric"]: fact for fact in extract_share_classes([text])}
    assert facts["ordinary_shares_outstanding"]["confidence"] < Decimal("0.8")


def test_single_class_note_is_ignored():
    assert extract_share_classes(["Stated capital\nOrdinary Shares 1,000,000 1,000,000\n"]) == []


def test_eps_times_total_shares_matches_attributable_profit():
    # Group profit attributable to equity holders is Rs. 701,929,6xx (income
    # statement, page 59 of the same report); EPS is Rs. 3.70.
    total = Decimal(189689990)
    assert float(Decimal("3.70") * total) == pytest.approx(701_929_600, rel=0.001)
    # The voting count alone does not reconcile (it was used before this fix).
    assert float(Decimal("3.70") * Decimal(165488271)) != pytest.approx(701_929_600, rel=0.05)
