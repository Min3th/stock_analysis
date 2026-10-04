from datetime import date
from pathlib import Path

from cse_screening.downloaders.financials import (
    CSEFinancialDocumentClient,
    filing_kind,
    parse_period_end,
)
from cse_screening.pipeline import _merge_documents


def test_financial_filing_title_classification_and_periods():
    assert filing_kind("Annual Report as at 31st March 2026") == "annual_report"
    assert filing_kind("Annual Report 2024/25") == "annual_report"
    assert (
        filing_kind("Interim Financial Statements for the Quarter ended 30th June 2026")
        == "interim_statement"
    )
    assert filing_kind("Errata to the Annual Report 2024/25") is None
    assert parse_period_end("Annual Report as at 31st March 2026") == date(2026, 3, 31)
    assert parse_period_end("ANNUAL REPORT AS OF 03/31/2025") == date(2025, 3, 31)
    assert parse_period_end("Annual Report 2024/25") == date(2025, 3, 31)
    assert parse_period_end("Interim Financial Statements - 30.06.2025") == date(2025, 6, 30)


def test_discovery_selects_latest_annual_and_interim_for_all_share_classes(
    tmp_path: Path, monkeypatch
):
    client = CSEFinancialDocumentClient(tmp_path)
    rows = [
        {
            "id": 1,
            "path": "old.pdf",
            "uploadedDate": "01 Jul 2025 01:00:00 PM",
            "fileText": "Annual Report 2024/25",
            "symbol": "RHL",
        },
        {
            "id": 2,
            "path": "annual.pdf",
            "uploadedDate": "31 Aug 2026 01:00:00 PM",
            "fileText": "Annual Report as at 31st March 2026",
            "symbol": "RHL",
        },
        {
            "id": 3,
            "path": "q1.pdf",
            "uploadedDate": "14 Aug 2026 01:00:00 PM",
            "fileText": "Interim Financial Statements for the Quarter ended 30th June 2026",
            "symbol": "RHL",
        },
    ]
    monkeypatch.setattr(client, "filings", lambda start, end: (rows, False))
    companies = [
        {"ticker": "RHL.N0000"},
        {"ticker": "RHL.X0000"},
    ]
    found, cached = client.discover(companies, date(2026, 10, 4))
    assert cached is False
    assert {item["kind"] for item in found["RHL.N0000"]} == {
        "annual_report",
        "interim_statement",
    }
    assert len([item for item in found["RHL.N0000"] if item["kind"] == "annual_report"]) == 2
    interim = next(item for item in found["RHL.X0000"] if item["kind"] == "interim_statement")
    assert interim["period_months"] == 3
    assert interim["comparative_period_end"] == date(2025, 6, 30)


def test_discovered_newer_document_replaces_configured_fallback():
    configured = [
        {
            "kind": "annual_report",
            "title": "Annual Report 2024/25",
            "period_end": date(2025, 3, 31),
            "publication_date": date(2025, 7, 1),
            "url": "https://company.example/old.pdf",
        }
    ]
    discovered = [
        {
            "kind": "annual_report",
            "title": "Annual Report 2025/26",
            "period_end": date(2026, 3, 31),
            "publication_date": date(2026, 7, 1),
            "url": "https://cdn.cse.lk/new.pdf",
            "discovery_url": "https://www.cse.lk/api/getFinancialAnnouncement",
        }
    ]
    assert _merge_documents(discovered, configured)[0]["url"].endswith("new.pdf")
