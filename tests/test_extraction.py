from decimal import Decimal as D

from cse_screening.extractors.statements import (
    extract_interim_flow_metrics,
    extract_metrics,
    extract_ordinary_shares,
    extract_total_debt,
)


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


def test_interim_flow_uses_current_and_prior_group_columns_after_label():
    pages = [
        (
            "STATEMENT OF PROFIT OR LOSS\n"
            "Consolidated Company Consolidated Company\n"
            "Audited Audited Unaudited Unaudited\n"
            "Year ended Year ended 3 months to 3 months to\n"
            "31.03.26 31.03.26 30.06.26 30.06.25\n"
            "Rs.'000 Rs.'000 Rs.'000 Rs.'000\n"
            "585,021,102 677,647 Revenue 4 179,324,938 130,363,159 38 184,714 158,920 16\n"
            "22,222,972 (1,435,851) Profit/ (Loss) for the period 5,922,554 3,177,311 86"
        )
    ]
    facts = {item["metric"]: item for item in extract_interim_flow_metrics(pages)}
    assert facts["revenue"]["value"] == D(179324938000)
    assert facts["revenue"]["comparatives"] == [D(179324938), D(130363159)]
    assert facts["net_profit"]["value"] == D(5922554000)


def test_inline_unit_overrides_missing_page_header_unit():
    pages = ["FINANCIAL HIGHLIGHTS\nRevenue generated Rs. mn 585,021 492,201"]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["revenue"]["value"] == D(585021000000)
    assert facts["revenue"]["original_unit"] == "LKR million"


def test_decimal_note_reference_is_not_extracted_as_revenue():
    pages = ["STATEMENT OF PROFIT OR LOSS\nRevenue 5.1 49,660,591,585 34,510,580,202"]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["revenue"]["value"] == D(49660591585)


def test_revenue_reserves_is_not_revenue():
    pages = [
        "STATEMENT OF FINANCIAL POSITION\nRevenue reserves 24,573,025 24,019,205",
        "STATEMENT OF PROFIT OR LOSS\nRevenue 10,000 9,000",
    ]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["revenue"]["value"] == D(10000)


def test_explicit_ebit_extraction():
    pages = [
        (
            "STATEMENT OF PROFIT OR LOSS\n"
            "(In Thousands of Rupees)\n"
            "Earnings Before Interest and Tax (EBIT) 6,732 7,914"
        )
    ]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["ebit"]["value"] == D(6732000)


def test_results_from_operating_activities_is_operating_profit():
    pages = [
        (
            "STATEMENT OF PROFIT OR LOSS\n"
            "(In Thousands of Rupees)\n"
            "Results from operating activities 2,526,504 (1,463,340)"
        )
    ]
    facts = {item["metric"]: item for item in extract_metrics(pages)}
    assert facts["operating_profit"]["value"] == D(2526504000)


def test_period_end_ordinary_shares_preferred_and_normalized():
    pages = [
        (
            "Weighted Average Number of Ordinary Shares (No. '000) 260,966 254,301\n"
            "Number of Ordinary Shares (No. '000) 278,900 253,546"
        )
    ]
    fact = extract_ordinary_shares(pages)
    assert fact["value"] == D(278900000)
    assert fact["notes"] == "Period-end ordinary shares."


def test_weighted_average_shares_is_explicit_fallback():
    pages = ["Weighted average number of ordinary shares in issue ('000) 212,625 212,625"]
    fact = extract_ordinary_shares(pages)
    assert fact["value"] == D(212625000)
    assert fact["confidence"] == D("0.78")


def test_wrapped_weighted_average_share_label_is_extracted():
    pages = [
        (
            "Weighted average number of ordinary shares in\n"
            "issue applicable to basic earnings per share 6,000,000 6,000,000"
        )
    ]
    fact = extract_ordinary_shares(pages)
    assert fact["value"] == D(6000000)
    assert fact["confidence"] == D("0.78")


def test_narrative_period_end_share_count_precedes_label():
    pages = [
        "The Stated Capital was Rs. 1,368,673,373 represented by\n1,107,893,840 Ordinary Shares."
    ]
    fact = extract_ordinary_shares(pages)
    assert fact["value"] == D(1107893840)
    assert fact["confidence"] == D("0.90")


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
