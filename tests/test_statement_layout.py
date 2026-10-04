from decimal import Decimal as D

from cse_screening.extractors.layout import (
    column_layout,
    locate_statements,
    page_unit,
    strip_note_reference,
    trailing_values,
)
from cse_screening.extractors.primary import reporting_period_months
from cse_screening.extractors.statements import (
    extract_document_metrics,
    extract_metrics,
    extract_ordinary_shares,
)

INCOME = (
    "STATEMENT OF PROFIT OR LOSS\n"
    "Group Company\n"
    "For the year ended 31 March Note 2026 2025 2026 2025\n"
    "Rs.'000 Rs.'000 Rs.'000 Rs.'000\n"
    "Revenue 4 45,507 37,486 22,858 17,330\n"
    "Cost of sales (33,000) (28,000) (17,000) (13,000)\n"
    "Gross profit 12,507 9,486 5,858 4,330\n"
    "Other income 5 844 206 983 411\n"
    "Administrative expenses (1,292) (1,147) (281) (283)\n"
    "Operating profit 9,178 7,466 4,987 3,387\n"
    "Finance costs 8 (128) (266) (111) (167)\n"
    "Profit before tax 9,050 7,200 4,876 3,220\n"
    "Income tax expense 9 (1,770) (1,781) (1,119) (812)\n"
    "Profit for the year 7,280 5,419 3,757 2,408\n"
    "Profit attributable to:\n"
    "Owners of the company 6,337 4,580 3,757 2,408\n"
    "Non-controlling interests 943 839 - -\n"
    "Earnings per share - basic/ diluted 10 8.82 6.37 5.23 3.35\n"
)
POSITION = (
    "STATEMENT OF FINANCIAL POSITION\n"
    "Group Company\n"
    "As at 31 March Note 2026 2025 2026 2025\n"
    "Rs.'000 Rs.'000 Rs.'000 Rs.'000\n"
    "Property, plant and equipment 12 9,000 8,000 4,000 3,500\n"
    "Inventories 20 15,000 12,000 6,000 5,000\n"
    "Trade and other receivables 21 12,000 10,000 5,000 4,000\n"
    "Cash and cash equivalents 24 1,637 2,077 404 1,056\n"
    "Total assets 52,842 43,653 22,559 18,710\n"
    "Stated capital 25 2,000 2,000 2,000 2,000\n"
    "Retained earnings 31,555 25,554 14,294 10,875\n"
    "Equity attributable to owners of the company 36,904 30,798 16,958 13,522\n"
    "Non-controlling interests 6,074 5,222 - -\n"
    "Total equity 42,978 36,020 16,958 13,522\n"
    "Borrowings 26 71 120 57 95\n"
    "Lease liabilities 18 4 - -\n"
    "Borrowings 26 2,107 1,265 1,525 688\n"
    "Bank overdrafts 500 300 - -\n"
    "Trade and other payables 27 5,000 4,000 2,000 1,500\n"
    "Total equity and liabilities 52,842 43,653 22,559 18,710\n"
)
CASH_FLOW = (
    "STATEMENT OF CASH FLOWS\n"
    "Group Company\n"
    "For the year ended 31 March Note 2026 2025 2026 2025\n"
    "Cash flows from operating activities\n"
    "Interest paid 8 (128) (266) (111) (167)\n"
    "Income tax paid 27 (2,670) (2,048) (1,137) (776)\n"
    "Net cash generated from / (used in) operating\n"
    "activities 1,434 3,928 (1,320) 1,475\n"
    "Cash flows from investing activities\n"
    "Purchase of property, plant and equipment 12 (355) (250) (26) (9)\n"
    "Net cash used in investing activities (300) (200) (20) (5)\n"
    "Net cash used in financing activities (1,500) (2,000) (500) (700)\n"
    "Net decrease in cash and cash equivalents (366) 1,728 (1,840) 770\n"
    "Cash and cash equivalents at the end of the year 1,137 1,777 404 1,056\n"
)
HIGHLIGHTS = (
    "FINANCIAL HIGHLIGHTS\n"
    "Revenue Rs. mn 99 12.70 88\n"
    "Total assets Rs. mn 77 5.00 66\n"
    "Net assets per share Rs. 150.95 21.55 124.19\n"
)


def _facts(pages):
    return {item["metric"]: item for item in extract_metrics(pages)}


def test_primary_statements_are_located_and_preferred_over_highlights():
    pages = [HIGHLIGHTS, "Chairman's review", INCOME, POSITION, CASH_FLOW]
    assert locate_statements(pages) == {"income": [3], "position": [4], "cash_flow": [5]}
    facts = _facts(pages)
    assert facts["revenue"]["value"] == D(45507000)
    assert facts["revenue"]["page"] == 3
    assert facts["revenue"]["statement_scope"] == "group"
    assert facts["total_assets"]["value"] == D(52842000)
    assert facts["eps"]["value"] == D("8.82")
    assert facts["net_profit_attributable"]["value"] == D(6337000)
    assert facts["bvps"]["value"] == D("150.95")


def test_cash_flow_page_without_a_unit_inherits_the_statement_unit():
    facts = _facts([INCOME, POSITION, CASH_FLOW])
    assert facts["operating_cash_flow"]["value"] == D(1434000)
    assert facts["operating_cash_flow"]["original_unit"] == "LKR '000"
    assert facts["operating_cash_flow"]["confidence"] == D("0.88")
    assert facts["capital_expenditure"]["value"] == D(-355000)


def test_missing_total_liabilities_row_is_derived_and_debt_excludes_leases():
    facts = _facts([INCOME, POSITION, CASH_FLOW])
    assert facts["total_liabilities"]["value"] == D(9864000)
    assert facts["total_liabilities"]["extraction_method"] == (
        "derived_total_assets_less_total_equity"
    )
    assert facts["ordinary_equity"]["value"] == D(36904000)
    assert facts["total_debt"]["value"] == D(2678000)
    assert facts["total_debt"]["comparatives"][1] == D(1685000)


def test_company_first_layout_reads_the_group_block():
    income = INCOME.replace("Group Company", "Company Group")
    facts = _facts([income, POSITION.replace("Group Company", "Company Group"), CASH_FLOW])
    assert facts["revenue"]["value"] == D(22858000)
    assert facts["revenue"]["comparatives"] == [D(22858), D(17330)]
    assert facts["revenue"]["statement_scope"] == "group"


def test_nil_dashes_keep_later_columns_aligned():
    income = INCOME.replace("Company Group", "Group Company").replace(
        "Revenue 4 45,507 37,486 22,858 17,330", "Total revenue 28 - - 149,345 122,095"
    )
    income = income.replace("Group Company", "Company Group")
    facts = _facts([income, POSITION.replace("Group Company", "Company Group"), CASH_FLOW])
    assert facts["revenue"]["value"] == D(149345000)


def test_foreign_currency_translation_is_not_the_primary_statement():
    translated = INCOME.replace("Rs.'000 Rs.'000 Rs.'000 Rs.'000", "US$ '000 US$ '000")
    pages = [INCOME, POSITION, CASH_FLOW, "Notes", translated.replace("45,507", "150")]
    assert locate_statements(pages)["income"] == [1]


def test_parent_equity_is_derived_when_only_the_minority_is_labelled():
    position = POSITION.replace(
        "Equity attributable to owners of the company 36,904 30,798 16,958 13,522\n", ""
    )
    facts = _facts([INCOME, position, CASH_FLOW])
    assert facts["ordinary_equity"]["value"] == D(36904000)
    assert facts["ordinary_equity"]["extraction_method"] == (
        "derived_total_equity_less_non_controlling_interest"
    )


def test_note_reference_is_recognised_by_form_not_size():
    cells = strip_note_reference(
        trailing_values("Dividend per share Rs. 6.00 0.00 6.00 5.35"), None
    )
    assert cells.values[0] == D("6.00")
    cells = strip_note_reference(trailing_values("Dividend per share 11 1.50 1.25 1.50 1.25"), None)
    assert cells.values[0] == D("1.50") and cells.note_reference == "11"
    cells = strip_note_reference(trailing_values("Basic Earnings Per Share 10.1 2.98 2.70"), 4)
    assert cells.values == [D("2.98"), D("2.70")]
    cells = strip_note_reference(trailing_values("Net assets per share 34.87 29.90 24.86"), None)
    assert cells.values[0] == D("34.87")


def test_label_numbers_and_bleeding_text_are_not_amount_cells():
    row = trailing_values(
        "Basic (Loss) / Earnings per Share (Rs.) (Restated 2025) 11.1 (2.91) (4.23) 4.92 2.87"
    )
    assert strip_note_reference(row, 4).values[0] == D("-2.91")
    row = trailing_values("Total equity 42,896 42,712 29,142 27,994 The Board is responsible")
    assert row.values == [D(42896), D(42712), D(29142), D(27994)]
    row = trailing_values("Basic 10 Rs. 1.46 Rs. 1.86")
    assert strip_note_reference(row, 4).values == [D("1.46"), D("1.86")]
    assert trailing_values("Basic Earnings Per Share (Rs.) 10.1 4.26 4.70* 4.02 3.52*").values[
        2
    ] == D("4.70")


def test_layout_handles_dated_headers_restated_columns_and_report_titles():
    layout = column_layout("Group Company\nAs at 31 March 2025 2025 2024 2025 2024\nRs.'000")
    assert layout.columns == 4 and layout.current_first
    layout = column_layout("GROUP COMPANY\nAs at 31st March, 2025 2024 2023 2025 2024\nRs.'000")
    assert layout.columns == 5 and layout.block_starts == (0, 3)
    layout = column_layout("ANNUAL REPORT 2025/2026\nGroup Company\nNotes 2026 2025 2026 2025")
    assert layout.current_first and layout.columns == 4


def test_unit_comes_from_header_or_explicit_sentence_not_narrative():
    narrative = "FINANCIAL CAPITAL\nEBITDA amounted to Rs. 26.6 Bn\nNote 2026 2025\nRs.'000 Rs.'000"
    assert page_unit(narrative + "\nRevenue 10 20")[0] == "LKR '000"
    footnote = "Income Statement\n2026 2025\nRevenue 42,326 32,275\nAll values are in Rupees '000s."
    assert page_unit(footnote) == ("LKR '000", D(1000))
    assert page_unit("NOTE 2026 (Rs.) 2025 (Rs.)\nRevenue 10 20") == ("LKR", D(1))


def test_share_count_scale_must_be_stated_on_the_share_row():
    pages = [
        (
            "Profit attributable to equity holders of the Parent (Rs.'000) 14,051,822 13,449,129\n"
            "Weighted average number of ordinary shares of the parent ( No.) 751,036,500 751,036,500"
        )
    ]
    assert extract_ordinary_shares(pages)["value"] == D(751036500)


def test_interim_period_is_read_from_the_header_with_variance_columns():
    interim = (
        "STATEMENT OF PROFIT OR LOSS\n"
        "Group Company\n"
        "Three months ended 30th June Three months ended 30th June\n"
        "In LKR 2026 2025 % 2026 2025 %\n"
        "Revenue 16,586 7,732 115 5,139 5,104 1\n"
        "Cost of sales (12,141) (5,360) 126 (4,114) (4,055) 1\n"
        "Gross profit 4,445 2,372 87 1,025 1,049 (2)\n"
        "Administrative expenses (600) (500) 20 (300) (290) 3\n"
        "Profit before tax 2,400 1,200 100 500 520 (4)\n"
        "Income tax expense (500) (300) 67 (100) (110) (9)\n"
        "Profit for the period 1,900 900 111 400 410 (2)\n"
    )
    facts = {
        item["metric"]: item for item in extract_document_metrics([interim], "interim_statement")
    }
    assert facts["revenue"]["comparatives"] == [D(16586), D(7732)]
    assert facts["revenue"]["period_months"] == 3
    assert facts["net_profit"]["value"] == D(1900)


def test_quarter_and_cumulative_blocks_select_the_year_to_date():
    interim = (
        "CONSOLIDATED INCOME STATEMENT\n"
        "Quarter ended 30 September Six months ended 30 September\n"
        "2026 2025 2026 2025\n"
        "Rs.'000 Rs.'000 Rs.'000 Rs.'000\n"
        "Revenue 100 90 210 180\n"
        "Cost of sales (60) (55) (125) (110)\n"
        "Gross profit 40 35 85 70\n"
        "Administrative expenses (10) (9) (21) (18)\n"
        "Profit before tax 30 26 64 52\n"
        "Income tax expense (6) (5) (13) (10)\n"
        "Profit for the period 24 21 51 42\n"
    )
    facts = {
        item["metric"]: item for item in extract_document_metrics([interim], "interim_statement")
    }
    assert facts["revenue"]["comparatives"] == [D(210), D(180)]
    assert facts["revenue"]["period_months"] == 6


def test_changed_year_end_is_reported_as_a_fifteen_month_period():
    header = (
        "Statement of Profit or Loss\nGroup Company\n"
        "01.01.2025 to 01.01.2024 to 01.01.2025 to 01.01.2024 to\n"
        "31.03.2026 31.12.2024 31.03.2026 31.12.2024\n"
        "Note (Rs.'000) (Rs.'000) (Rs.'000) (Rs.'000)\n"
        "Revenue 4 36,196 25,000 30,000 21,000\n"
    )
    assert reporting_period_months(header) == 15
    assert reporting_period_months(INCOME) is None
