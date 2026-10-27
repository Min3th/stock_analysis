"""End-to-end offline run over a fixture cache: no network, one issuer, real statement pages."""

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from cse_screening.pipeline import load_pipeline_config, run

REPO = Path(__file__).parent.parent
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "EBCR.N0000"
    / "annual_report_as_at_31st_march_2026"
    / "pages.json"
)
FILING_PATH = "cmt/fixture/EBCR-annual-report-2026.pdf"
FILING_URL = f"https://cdn.cse.lk/{FILING_PATH}"


@pytest.fixture
def cache_root(tmp_path):
    """A repository root whose data/raw cache holds everything an offline run reads."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    (tmp_path / "config" / "companies.yml").write_text(
        "universe: {}\ncompanies: []\n", encoding="utf-8"
    )
    (tmp_path / "config" / "corrections.yml").write_text("corrections: []\n", encoding="utf-8")
    settings = load_pipeline_config(tmp_path / "config")
    raw = tmp_path / "data" / "raw"

    group = {
        "sector_id": 1,
        "sector_name": "Capital Goods",
        "industry_group_id": 1,
        "industry_group": "Capital Goods",
    }
    company = {
        "ticker": "EBCR.N0000",
        "name": "E B CREASY & COMPANY PLC",
        "sector": "Capital Goods",
        "gics_sector": "Industrials",
        "industry_group": "Capital Goods",
        "profile_url": "https://www.cse.lk/example",
        "classification_source_url": "https://www.cse.lk/gics",
        "documents": [],
        "market_data": {
            "price": 50,
            "market_cap": 5_000_000_000,
            "share_volume": 1000,
            "trade_volume": 10,
            "turnover": 50000,
            "last_traded_time": None,
            "market_source_url": "https://www.cse.lk/api/gics_sector_companies",
        },
    }
    (raw / "cse_universe").mkdir(parents=True)
    (raw / "cse_universe" / "capital_goods.json").write_text(
        json.dumps({"group": group, "companies": [company]}), encoding="utf-8"
    )
    (raw / "cse_financial_announcements").mkdir()
    (raw / "cse_financial_announcements" / "2023-01-01_2026-12-31.json").write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "symbol": "EBCR",
                    "fileText": "Annual Report as at 31st March 2026",
                    "path": FILING_PATH,
                    "authorizedDate": "10 Aug 2026 10:00:00 AM",
                }
            ]
        ),
        encoding="utf-8",
    )
    (raw / "cse_announcements").mkdir()
    (raw / "cse_announcements" / "feed.json").write_text("[]", encoding="utf-8")

    # A stand-in PDF plus the parsed-page cache that sits beside it.
    pdf = raw / "EBCR_N0000" / f"{hashlib.sha256(FILING_URL.encode()).hexdigest()[:16]}.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 fixture")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    count = max(int(number) for number in fixture["pages"])
    pages = [fixture["pages"].get(str(number), "") for number in range(1, count + 1)]
    cache_key = {
        "ocr_enabled": bool(settings["ocr"]["enabled"]),
        "minimum_text_characters_per_page": int(
            settings["ocr"]["minimum_text_characters_per_page"]
        ),
        "table_enabled": bool(settings["tables"]["enabled"]),
    }
    pdf.with_suffix(".pdf.pages.v2.json").write_text(
        json.dumps(
            {
                "version": 2,
                "settings": cache_key,
                "pages": pages,
                "methods": ["native_text"] * count,
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_offline_run_writes_reports_run_directory_and_lineage(cache_root):
    outputs = run(
        "2026Q3",
        "Capital Goods",
        None,
        cache_root,
        offline=True,
        run_dir=cache_root / "runs" / "e2e",
    )

    # Nothing is empty, and the per-sector files carry the sector and period.
    for kind in ("xlsx", "csv", "review", "warnings", "markdown", "run_manifest"):
        assert outputs[kind].stat().st_size > 0, kind
    assert outputs["review"].name == "Capital_Goods_Manual_Review_2026_Q3.csv"

    screening = pd.read_csv(outputs["csv"])
    assert screening["Ticker"].tolist() == ["EBCR.N0000"]
    row = screening.iloc[0]
    assert row["Revenue"] == 35_356_836_000
    assert row["Net Profit"] == 1_216_660_000
    assert row["EPS"] == pytest.approx(4.26)
    assert row["Income Period Basis"] == "FY to 2026-03-31"
    assert row["Current Price"] == 50

    # Every ratio keeps its formula and the fact ids it was built from.
    ratios = pd.read_excel(outputs["xlsx"], sheet_name="03_Ratios")
    pe_row = ratios[ratios["Metric"] == "P/E"].iloc[0]
    assert pe_row["Formula"] == "Current market price / EPS"
    assert pe_row["Value"] == pytest.approx(50 / 4.26)
    assert "EBCR.N0000:" in str(pe_row["Input Fact IDs"])

    # The source is recorded with its checksum and where it came from.
    sources = pd.read_excel(outputs["xlsx"], sheet_name="06_Sources")
    document = sources[sources["Type"] == "annual_report"].iloc[0]
    assert document["Source URL"] == FILING_URL
    assert len(str(document["SHA256"])) == 64
    assert document["Source Type"] == "cse_or_configured"

    # Withheld and missing values are listed for review, not silently dropped.
    review = pd.read_csv(outputs["review"])
    assert "missing_metric" in set(review["Validation Rule"])

    manifest = json.loads(outputs["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["status"] == "ok" and manifest["offline"] is True
    assert manifest["counts"]["screening"] == 1
    screening_json = json.loads((cache_root / "runs" / "e2e" / "screening.json").read_text("utf-8"))
    assert screening_json[0]["Ticker"] == "EBCR.N0000"


def test_offline_run_is_repeatable(cache_root):
    first = run("2026Q3", "Capital Goods", None, cache_root, offline=True)
    first_csv = first["csv"].read_text(encoding="utf-8")
    second = run("2026Q3", "Capital Goods", None, cache_root, offline=True)
    assert second["csv"].read_text(encoding="utf-8") == first_csv


def test_offline_run_without_a_universe_cache_fails_clearly(cache_root):
    shutil.rmtree(cache_root / "data" / "raw" / "cse_universe")
    with pytest.raises(OSError, match="Offline mode"):
        run("2026Q3", "Capital Goods", None, cache_root, offline=True)
