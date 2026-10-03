from decimal import Decimal as D

from cse_screening.extractors.statements import extract_metrics, extract_total_debt


def test_eps_extraction_preserves_negative_value():
    pages = ["STATEMENT OF PROFIT OR LOSS\nBasic earnings per share (2.45) 1.20"]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["eps"]["value"] == D("-2.45")


def test_note_level_cash_flow_and_retained_earnings():
    pages = [
        (
            "STATEMENT OF FINANCIAL POSITION\n(all amounts in Sri Lanka Rupees thousands)\n"
            "Retained earnings 31,555 25,554\nTotal liabilities 9,864 7,633\nCurrent liabilities"
        ),
        (
            "STATEMENT OF CASH FLOWS\n(all amounts in Sri Lanka Rupees thousands)\n"
            "Net cash generated from operating activities 1,434 3,928\n"
            "Purchase of property, plant and equipment (355) (250)"
        ),
    ]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["retained_earnings"]["value"] == D(31555000)
    assert facts["operating_cash_flow"]["value"] == D(1434000)
    assert facts["capital_expenditure"]["value"] == D(-355000)


def test_total_debt_sums_current_and_non_current_without_leases():
    pages = [
        (
            "STATEMENT OF FINANCIAL POSITION\n(all amounts in Sri Lanka Rupees thousands)\n"
            "Non-current liabilities\nBorrowings 26 71,712 120,319\nLease liabilities 18,474 409\n"
            "Current liabilities\nBorrowings 26 2,107,987 1,265,180\nTotal liabilities 9,864,938 7,633,711"
        )
    ]
    debt = extract_total_debt(pages)
    assert debt is not None
    assert debt["value"] == D(2179699000)
    assert debt["comparatives"][1] == D(1385499000)


def test_primary_statement_is_preferred_over_financial_highlights():
    pages = [
        "FINANCIAL HIGHLIGHTS\nTotal assets 100 50 90 45",
        "STATEMENT OF FINANCIAL POSITION\nTotal assets 100 90 50 45",
    ]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["total_assets"]["page"] == 2
    assert facts["total_assets"]["comparatives"][:2] == [D(100), D(90)]
