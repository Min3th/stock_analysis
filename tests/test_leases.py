import json
from decimal import Decimal
from pathlib import Path

from cse_screening.extractors.statements import extract_document_metrics

FIXTURE = Path(__file__).parent / "fixtures" / "leases" / "acl_position.json"


def test_current_and_non_current_lease_liabilities_are_summed_apart_from_debt():
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))["pages"]
    facts = {fact["metric"]: fact for fact in extract_document_metrics(pages, "annual_report")}
    # Non-current 18,474 + current 8,669, Rs. '000, Group 2026 column.
    assert facts["lease_liabilities"]["value"] == Decimal(27143000)
    assert facts["lease_liabilities"]["previous_value"] == Decimal(9355000)
    assert "Lease liabilities" in facts["lease_liabilities"]["source_text"]
    # Leases are not folded into total debt.
    assert "lease" not in facts["total_debt"]["source_text"].casefold()
