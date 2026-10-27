import json
from datetime import date

import pytest
import yaml

import main as cli
from cse_screening.corrections import append_correction, load_corrections
from cse_screening.downloaders.announcements import CSEDividendClient
from cse_screening.downloaders.financials import CSEFinancialDocumentClient
from cse_screening.downloaders.http import CachedDownloader, get_market_data
from cse_screening.downloaders.universe import CSEUniverseClient

ENTRY = {
    "ticker": "AAA.N0000",
    "metric": "revenue",
    "financial_period": "2026-03-31",
    "source_document": "Annual Report 2026",
    "value": "1500",
    "unit": "LKR million",
    "source_page": 12,
    "statement_scope": "group",
    "reason": "Digit misread by OCR",
    "author": "reviewer",
    "corrected_at": "2026-10-27",
}


def test_offline_downloader_never_touches_the_network(tmp_path):
    downloader = CachedDownloader(tmp_path, offline=True)
    with pytest.raises(OSError, match="Offline mode"):
        downloader.download("AAA.N0000", "https://example.invalid/a.pdf", "Annual Report")


def test_offline_clients_raise_on_cache_miss(tmp_path):
    with pytest.raises(OSError):
        CSEUniverseClient(cache_root=tmp_path, offline=True).companies("Banks")
    with pytest.raises(OSError):
        CSEFinancialDocumentClient(tmp_path, offline=True).filings(
            date(2023, 1, 1), date(2026, 1, 1)
        )
    with pytest.raises(OSError):
        CSEDividendClient(tmp_path, offline=True).latest_for_companies([])
    with pytest.raises(OSError):
        get_market_data("AAA.N0000", tmp_path, offline=True)


def test_offline_universe_reads_the_cached_response(tmp_path):
    cache = tmp_path / "cse_universe"
    cache.mkdir()
    payload = {"group": {"industry_group": "Banks"}, "companies": [{"ticker": "AAA.N0000"}]}
    (cache / "banks.json").write_text(json.dumps(payload), encoding="utf-8")
    group, companies = CSEUniverseClient(cache_root=tmp_path, offline=True).companies("Banks")
    assert group["industry_group"] == "Banks"
    assert companies == [{"ticker": "AAA.N0000"}]


def test_offline_filing_feed_uses_newest_cached_window(tmp_path):
    cache = tmp_path / "cse_financial_announcements"
    cache.mkdir()
    (cache / "2023-01-01_2026-01-01.json").write_text('[{"id": 1}]', encoding="utf-8")
    (cache / "2023-06-01_2026-06-01.json").write_text('[{"id": 2}]', encoding="utf-8")
    rows, cached = CSEFinancialDocumentClient(tmp_path, offline=True).filings(
        date(2024, 1, 1), date(2027, 1, 1)
    )
    assert rows == [{"id": 2}] and cached


def test_append_correction_is_append_only_and_supersedes(tmp_path):
    path = tmp_path / "corrections.yml"
    path.write_text("# header kept\ncorrections: []\n", encoding="utf-8")
    first = append_correction(path, dict(ENTRY))
    second = append_correction(path, {**ENTRY, "value": "1600"}, supersedes=first["id"])
    items = load_corrections(path)
    assert [item["id"] for item in items] == [first["id"], second["id"]]
    assert items[0]["status"] == "superseded" and items[0]["superseded_by"] == second["id"]
    assert items[0]["value"] == "1500"
    assert items[1]["status"] == "active" and items[1]["supersedes"] == first["id"]
    assert path.read_text(encoding="utf-8").startswith("# header kept")


def test_append_correction_rejects_bad_input_without_changing_the_file(tmp_path):
    path = tmp_path / "corrections.yml"
    path.write_text("corrections: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        append_correction(path, {**ENTRY, "value": "not-a-number"})
    with pytest.raises(ValueError):
        append_correction(path, dict(ENTRY), supersedes="missing")
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {"corrections": []}
    assert not path.with_name("corrections.yml.tmp").exists()


def test_bare_flags_still_mean_run(monkeypatch):
    seen = {}

    def fake_run(period, sector, company, root, corrections, offline, run_dir):
        seen.update(period=period, sector=sector, company=company, offline=offline)
        return {}

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["--sector", "Banks", "--period", "2026q3", "--offline"])
    assert seen == {"period": "2026Q3", "sector": "Banks", "company": None, "offline": True}


def test_corrections_add_command_writes_the_file(tmp_path, capsys):
    path = tmp_path / "corrections.yml"
    path.write_text("corrections: []\n", encoding="utf-8")
    cli.main(
        [
            "corrections",
            "add",
            "--ticker",
            "AAA.N0000",
            "--metric",
            "revenue",
            "--value",
            "1500",
            "--unit",
            "LKR million",
            "--period-end",
            "2026-03-31",
            "--document",
            "Annual Report 2026",
            "--source-page",
            "12",
            "--reason",
            "OCR digit",
            "--file",
            str(path),
        ]
    )
    assert "correction: AAA.N0000-revenue-2026-03-31-1" in capsys.readouterr().out
    assert len(load_corrections(path)) == 1


def test_extract_rejects_a_non_pdf(tmp_path):
    fake = tmp_path / "a.pdf"
    fake.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(
            ["extract", "--pdf", str(fake), "--kind", "annual_report", "--period-end", "2026-03-31"]
        )
