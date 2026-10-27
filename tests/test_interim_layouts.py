import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_screening.extractors.layout import locate_statements, normalize_text
from cse_screening.extractors.statements import extract_document_metrics
from cse_screening.periods import ttm_from_annual_and_ytd

FIXTURES = Path(__file__).parent / "fixtures" / "interims"


def _facts(name: str) -> dict[str, dict]:
    pages = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["pages"]
    facts = extract_document_metrics(pages, "interim_statement", "bank")
    return {fact["metric"]: fact for fact in facts}


def test_half_year_with_quarter_block_reads_the_six_month_column():
    # "For the Six Months ended 30th June | For the Quarter ended 30th June"
    facts = _facts("pabc_h1.json")
    assert facts["revenue"]["value"] == Decimal(8677955000)  # not the quarter's 4,315,421
    assert facts["net_profit"]["value"] == Decimal(2502057000)
    assert facts["eps"]["value"] == Decimal("5.65")
    assert facts["net_profit"]["period_months"] == 6
    # Prior-year six months is what a TTM subtracts.
    assert facts["net_profit"]["previous_value"] == Decimal(2151911000)


def test_cumulative_first_layout_is_marked_year_to_date():
    # "For the Period ended | For the quarter ended"
    facts = _facts("sdb_h1.json")
    assert facts["revenue"]["value"] == Decimal(4557465000)  # not the quarter's 2,336,319
    assert facts["net_profit"]["value"] == Decimal(106815000)
    assert facts["net_profit"]["period_months"] == 0
    assert facts["net_profit"]["previous_value"] == Decimal(156123000)


def test_nine_month_statement_is_not_confirmed_without_a_period_length():
    # Ten columns (Bank/Group x period/quarter x year) and "Period ended" headers.
    facts = _facts("ndb_9m.json")
    assert facts["net_profit"]["value"] == Decimal(7711356000)
    assert facts["net_profit"].get("period_months") is None
    assert facts["net_profit"]["confidence"] < Decimal("0.9")


def test_restatement_note_is_not_taken_for_the_income_statement():
    pages = json.loads((FIXTURES / "ndb_9m.json").read_text(encoding="utf-8"))["pages"]
    assert "income" not in locate_statements([normalize_text(page) for page in pages])
    facts = _facts("ndb_9m.json")
    assert all(fact["page"] != 2 for fact in facts.values())


def test_ttm_uses_the_year_to_date_and_prior_year_to_date():
    facts = _facts("pabc_h1.json")["net_profit"]
    annual = Decimal(4_000_000_000)
    ttm = ttm_from_annual_and_ytd(
        annual,
        facts["value"],
        facts["previous_value"],
        annual_end=date(2025, 12, 31),
        current_end=date(2026, 6, 30),
        prior_end=date(2025, 6, 30),
        months=6,
    )
    assert ttm == annual + Decimal(2502057000) - Decimal(2151911000)
