from datetime import date
from pathlib import Path

import pytest

from cse_screening.downloaders.ir import (
    discover_ir_documents,
    parse_ir_page,
    same_site,
)
from cse_screening.pipeline import _merge_documents

PAGE = (Path(__file__).parent / "fixtures" / "ir" / "sample_ir_page.html").read_text(
    encoding="utf-8"
)
IR_URL = "https://www.example.lk/investors"


def test_only_same_domain_financial_report_pdfs_are_kept():
    documents = parse_ir_page(PAGE, IR_URL)
    by_url = {item["url"]: item for item in documents}
    assert set(by_url) == {
        "https://www.example.lk/wp-content/uploads/2026/07/Annual-Report-31st-March-2026.pdf",
        "https://ir.example.lk/files/AR-2025.pdf",
        "https://www.example.lk/files/Q1-30-06-2026.pdf",
        # Kind from the link text, period end from the file name.
        "https://www.example.lk/files/Q2-30-09-2026.pdf",
    }
    assert all(item["source_type"] == "issuer_ir" for item in documents)
    assert all(item["publication_date"] is None for item in documents)
    assert by_url["https://ir.example.lk/files/AR-2025.pdf"]["period_end"] == date(2025, 3, 31)


def test_same_site_rules():
    assert same_site("https://ir.example.lk/a.pdf", "https://www.example.lk/")
    assert same_site("https://example.lk/a.pdf", "https://www.example.lk/")
    assert not same_site("https://example.lk.evil.com/a.pdf", "https://www.example.lk/")
    assert not same_site("https://notexample.lk/a.pdf", "https://www.example.lk/")


def test_interim_gets_its_length_from_the_annual_year_end(tmp_path):
    cache = tmp_path / "issuer_ir"
    cache.mkdir()
    (cache / "EXA_N0000.html").write_text(PAGE, encoding="utf-8")
    documents = discover_ir_documents(IR_URL, "EXA.N0000", tmp_path, offline=True)
    interims = {
        item["period_end"]: item for item in documents if item["kind"] == "interim_statement"
    }
    assert interims[date(2026, 6, 30)]["period_months"] == 3
    assert interims[date(2026, 6, 30)]["comparative_period_end"] == date(2025, 6, 30)
    assert interims[date(2026, 9, 30)]["period_months"] == 6


def test_offline_without_a_cached_page_raises(tmp_path):
    with pytest.raises(OSError, match="Offline mode"):
        discover_ir_documents(IR_URL, "EXA.N0000", tmp_path, offline=True)


def test_ir_documents_rank_below_cse_and_configured_and_uploads():
    base = {
        "kind": "annual_report",
        "period_end": date(2026, 3, 31),
        "publication_date": "2099-01-01",
    }
    ir = {
        **base,
        "title": "IR copy",
        "url": "https://www.example.lk/ar.pdf",
        "source_type": "issuer_ir",
    }
    configured = {**base, "title": "Configured", "url": "https://x/ar.pdf"}
    upload = {**base, "title": "Upload", "url": "upload://abc", "source_type": "user_upload"}
    assert _merge_documents([], [ir, configured])[0]["title"] == "Configured"
    assert _merge_documents([], [ir, upload])[0]["title"] == "Upload"
    assert _merge_documents([], [ir])[0]["title"] == "IR copy"
