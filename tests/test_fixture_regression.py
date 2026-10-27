"""Hand-checked statement fixtures: the extractors must reproduce the recorded figures.

Each ``tests/fixtures/<TICKER>/<document>/`` holds ``pages.json`` (page text of the
located statements, keyed by the report's own page number) and ``expected.yml``
(the printed figures with their pages). Two layers are checked: every recorded
value, and the accounting identity ``assets = liabilities + equity`` wherever the
fixture holds all three.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from cse_screening.extractors.statements import extract_document_metrics

ROOT = Path(__file__).parent / "fixtures"
CASES = sorted(path.parent for path in ROOT.glob("*/*/expected.yml"))


def _facts(folder: Path) -> tuple[dict, dict[str, dict]]:
    pages = json.loads((folder / "pages.json").read_text(encoding="utf-8"))
    expected = yaml.safe_load((folder / "expected.yml").read_text(encoding="utf-8"))
    count = max(int(number) for number in pages["pages"])
    # Extractors address pages by position, so keep the report's own numbering.
    text = [pages["pages"].get(str(number), "") for number in range(1, count + 1)]
    facts = extract_document_metrics(text, "annual_report", expected["profile"])
    return expected, {fact["metric"]: fact for fact in facts}


def test_the_scale_up_gate_fixtures_are_present():
    layouts = {
        json.loads((case / "pages.json").read_text(encoding="utf-8"))["layout"] for case in CASES
    }
    assert {"digital", "difficult_table", "ocr", "bank"} <= layouts


@pytest.mark.parametrize("folder", CASES, ids=lambda path: f"{path.parent.name}/{path.name[:30]}")
def test_extracted_values_match_the_recorded_figures(folder):
    expected, facts = _facts(folder)
    for item in expected["facts"]:
        fact = facts.get(item["metric"])
        assert fact is not None, f"{item['metric']} was not extracted"
        assert fact["value"] == Decimal(item["value"]), item["metric"]
        assert fact["page"] == item["page"], item["metric"]
        assert fact["confidence"] >= Decimal("0.8"), item["metric"]


@pytest.mark.parametrize("folder", CASES, ids=lambda path: f"{path.parent.name}/{path.name[:30]}")
def test_recorded_figures_satisfy_the_balance_identity(folder):
    expected, _ = _facts(folder)
    values = {item["metric"]: Decimal(item["value"]) for item in expected["facts"]}
    if {"total_assets", "total_liabilities", "total_equity"} <= values.keys():
        assert values["total_assets"] == values["total_liabilities"] + values["total_equity"]
    if "total_assets" in values and "total_liabilities" in values and "total_equity" not in values:
        # Equity attributable to owners equals the difference when there is no
        # non-controlling interest (ASHO prints it as equal).
        assert values["total_assets"] > values["total_liabilities"]
