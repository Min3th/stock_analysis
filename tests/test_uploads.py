import hashlib
from datetime import date

import pytest

from cse_screening.downloaders.local import (
    load_upload_records,
    register_upload,
    upload_documents,
)
from cse_screening.pipeline import _merge_documents, _read_upload


def _pdf(path, body=b"%PDF-1.4 minimal"):
    path.write_bytes(body)
    return path


def _register(tmp_path, **overrides):
    cache = tmp_path / "data" / "raw"
    arguments = {
        "kind": "annual_report",
        "period_end": date(2026, 3, 31),
        "allowed_tickers": {"AAA.N0000"},
    }
    arguments.update(overrides)
    return register_upload(
        tmp_path,
        cache,
        tmp_path / "config" / "uploads.yml",
        overrides.pop("ticker", "AAA.N0000"),
        _pdf(tmp_path / "Report (final).pdf"),
        **{k: v for k, v in arguments.items() if k != "ticker"},
    )


def test_upload_is_stored_by_checksum_with_provenance(tmp_path):
    record = _register(tmp_path, title="Annual Report 2026")
    checksum = hashlib.sha256(b"%PDF-1.4 minimal").hexdigest()
    assert record["sha256"] == checksum
    assert record["path"] == f"data/raw/AAA_N0000/uploads/{checksum[:16]}.pdf"
    assert record["original_filename"] == "Report (final).pdf"
    renamed = _register(tmp_path, title="Renamed", original_filename="../../Client copy.pdf")
    # Same file content, so the first record is returned; the name is only stored once.
    assert renamed == record
    assert record["source_type"] == "user_upload"
    stored = tmp_path / record["path"]
    assert stored.read_bytes() == b"%PDF-1.4 minimal"
    assert load_upload_records(tmp_path / "config" / "uploads.yml") == [record]


def test_same_file_is_not_recorded_twice(tmp_path):
    first = _register(tmp_path)
    second = _register(tmp_path)
    assert first == second
    assert len(load_upload_records(tmp_path / "config" / "uploads.yml")) == 1


def test_upload_validation(tmp_path):
    with pytest.raises(ValueError, match="not in the known CSE universe"):
        register_upload(
            tmp_path,
            tmp_path / "raw",
            tmp_path / "u.yml",
            "ZZZ.N0000",
            _pdf(tmp_path / "a.pdf"),
            kind="annual_report",
            period_end=date(2026, 3, 31),
            allowed_tickers={"AAA.N0000"},
        )
    with pytest.raises(ValueError, match="not a PDF"):
        register_upload(
            tmp_path,
            tmp_path / "raw",
            tmp_path / "u.yml",
            "AAA.N0000",
            _pdf(tmp_path / "b.pdf", b"<html>"),
            kind="annual_report",
            period_end=date(2026, 3, 31),
        )
    with pytest.raises(ValueError, match="period_months"):
        _register(tmp_path, kind="interim_statement")
    with pytest.raises(ValueError, match="not a CSE ticker"):
        register_upload(
            tmp_path,
            tmp_path / "raw",
            tmp_path / "u.yml",
            "../evil",
            _pdf(tmp_path / "c.pdf"),
            kind="annual_report",
            period_end=date(2026, 3, 31),
        )
    assert not (tmp_path / "u.yml").exists()


def test_official_filing_beats_an_upload_for_the_same_period(tmp_path):
    _register(tmp_path, title="My copy")
    upload = upload_documents(tmp_path / "config" / "uploads.yml", tmp_path)["AAA.N0000"]
    official = {
        "kind": "annual_report",
        "title": "Annual Report 2026",
        "period_end": date(2026, 3, 31),
        "publication_date": None,
        "url": "https://cdn.cse.lk/a.pdf",
        "discovery_url": "x",
    }
    merged = _merge_documents([official], upload)
    assert [item["title"] for item in merged] == ["Annual Report 2026"]
    only_upload = _merge_documents([], upload)
    assert only_upload[0]["source_type"] == "user_upload"


def test_changed_upload_is_refused(tmp_path):
    _register(tmp_path)
    document = upload_documents(tmp_path / "config" / "uploads.yml", tmp_path)["AAA.N0000"][0]
    assert _read_upload(document)[1] == document["sha256"]
    with open(document["local_file"], "ab") as handle:
        handle.write(b" tampered")
    with pytest.raises(ValueError, match="checksum"):
        _read_upload(document)
