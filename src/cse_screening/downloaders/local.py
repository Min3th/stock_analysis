"""User-supplied filings: validated, stored by checksum and listed in ``uploads.yml``.

An upload is a document fallback only. It never changes membership metadata, and
an official CSE filing for the same period always wins in ``_merge_documents``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

TICKER = re.compile(r"^[A-Z]+\.[NXRWP]\d{4}$")
KINDS = {"annual_report", "interim_statement"}
UPLOAD_SCHEME = "upload://"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def known_tickers(root: Path, cache_directory: str = "data/raw") -> set[str]:
    """Tickers in any cached official universe plus the configured fallbacks."""
    tickers: set[str] = set()
    for path in (root / cache_directory / "cse_universe").glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tickers.update(item["ticker"] for item in payload.get("companies", []))
    companies = root / "config" / "companies.yml"
    if companies.exists():
        config = yaml.safe_load(companies.read_text(encoding="utf-8")) or {}
        tickers.update(item["ticker"] for item in config.get("companies", []))
    return tickers


def register_upload(
    root: Path,
    cache_root: Path,
    uploads_path: Path,
    ticker: str,
    source: Path,
    *,
    kind: str,
    period_end: date,
    title: str | None = None,
    period_months: int | None = None,
    publication_date: date | None = None,
    allowed_tickers: set[str] | None = None,
) -> dict:
    """Copy a PDF into the cache and append its provenance record; return it.

    ``root`` is the repository root; the stored path is recorded relative to it.
    """
    if not TICKER.match(ticker):
        raise ValueError(f"{ticker!r} is not a CSE ticker such as ACL.N0000")
    if allowed_tickers is not None and ticker not in allowed_tickers:
        raise ValueError(f"{ticker} is not in the known CSE universe; upload rejected")
    if kind not in KINDS:
        raise ValueError("kind must be annual_report or interim_statement")
    if kind == "interim_statement" and not period_months:
        raise ValueError("an interim_statement upload needs period_months")
    content = source.read_bytes()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("file is larger than the 50 MB upload limit")
    if not content.startswith(b"%PDF"):
        raise ValueError(f"{source.name} is not a PDF (missing %PDF header)")
    checksum = hashlib.sha256(content).hexdigest()
    records = load_upload_records(uploads_path)
    existing = next((r for r in records if r["sha256"] == checksum and r["ticker"] == ticker), None)
    if existing is not None:
        return existing
    stored = cache_root / ticker.replace(".", "_") / "uploads" / f"{checksum[:16]}.pdf"
    stored.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, stored)
    record = {
        "ticker": ticker,
        "kind": kind,
        "title": title or source.stem,
        "period_end": period_end,
        "publication_date": publication_date,
        "sha256": checksum,
        "path": stored.relative_to(root).as_posix(),
        "original_filename": source.name,
        "uploaded_utc": datetime.now(UTC).isoformat(),
        "source_type": "user_upload",
    }
    if period_months:
        record["period_months"] = int(period_months)
    uploads_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump({"uploads": [*records, record]}, sort_keys=False, allow_unicode=True)
    uploads_path.write_text(
        "# Append-only list of user-supplied filings. Written by `main.py uploads add`.\n"
        + rendered,
        encoding="utf-8",
    )
    return record


def load_upload_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = payload.get("uploads") or []
    required = {"ticker", "kind", "title", "period_end", "sha256", "path"}
    for index, item in enumerate(records, 1):
        missing = required - item.keys()
        if missing:
            raise ValueError(f"{path}: upload #{index} missing {', '.join(sorted(missing))}")
    return records


def upload_documents(path: Path, root: Path) -> dict[str, list[dict]]:
    """Uploads as pipeline documents keyed by ticker (``url`` is a stable pseudo-URL)."""
    documents: dict[str, list[dict]] = {}
    for record in load_upload_records(path):
        document = {
            "kind": record["kind"],
            "title": record["title"],
            "period_end": record["period_end"],
            "publication_date": record.get("publication_date"),
            "url": f"{UPLOAD_SCHEME}{record['sha256'][:16]}",
            "source_type": "user_upload",
            "local_file": str(root / record["path"]),
            "sha256": record["sha256"],
            "original_filename": record.get("original_filename"),
            "uploaded_utc": record.get("uploaded_utc"),
        }
        if record.get("period_months"):
            document["period_months"] = record["period_months"]
            document["comparative_period_end"] = _prior_year(record["period_end"])
        documents.setdefault(record["ticker"], []).append(document)
    return documents


def _prior_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)
