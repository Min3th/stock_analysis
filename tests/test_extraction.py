from decimal import Decimal as D

from cse_screening.extractors.statements import extract_metrics


def test_eps_extraction_preserves_negative_value():
    pages = ["STATEMENT OF PROFIT OR LOSS\nBasic earnings per share (2.45) 1.20"]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["eps"]["value"] == D("-2.45")
