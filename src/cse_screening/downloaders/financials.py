"""Discover latest official company financial filings from the CSE archive."""

from __future__ import annotations

import json
import re
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .universe import CSE_API

FINANCIAL_ENDPOINT = f"{CSE_API}/getFinancialAnnouncement"
EXCLUDED_TITLES = re.compile(
    r"\b(?:errata|trust deed|prospectus|articles? of association|accountants?' report|"
    r"key investor information|bond framework)\b",
    re.IGNORECASE,
)
ANNUAL_TITLE = re.compile(r"\b(?:annual report|audited financial statements?)\b", re.IGNORECASE)
INTERIM_TITLE = re.compile(
    r"\b(?:interim|quarterly|quarter ended|financial statements? for the quarter)\b",
    re.IGNORECASE,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def filing_kind(title: str) -> str | None:
    if EXCLUDED_TITLES.search(title):
        return None
    if ANNUAL_TITLE.search(title):
        return "annual_report"
    if INTERIM_TITLE.search(title):
        return "interim_statement"
    return None


def parse_period_end(title: str) -> date | None:
    normalized = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", title, flags=re.IGNORECASE)
    patterns = (
        r"\b(\d{1,2})[ ./-](\d{1,2})[ ./-](20\d{2})\b",
        r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b",
    )
    match = re.search(patterns[0], normalized)
    if match:
        first, second, year = map(int, match.groups())
        # CSE titles use both DD/MM/YYYY and MM/DD/YYYY. Values above 12 resolve
        # the order; ambiguous dates retain the prevailing day-first convention.
        month, day = (first, second) if second > 12 else (second, first)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    match = re.search(patterns[1], normalized)
    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2)[:3].casefold())
        return date(int(match.group(3)), month, day) if month else None
    year_range = re.search(r"\b(20\d{2})\s*/\s*(\d{2,4})\b", normalized)
    if year_range and filing_kind(title) == "annual_report":
        end_year = int(year_range.group(2))
        if end_year < 100:
            end_year += 2000
        return date(end_year, 3, 31)
    return None


def _uploaded_date(value: str | None) -> date | None:
    if not value:
        return None
    return (
        datetime.strptime(value, "%d %b %Y %I:%M:%S %p")
        .replace(tzinfo=ZoneInfo("Asia/Colombo"))
        .date()
    )


def _months_since(annual_end: date, interim_end: date) -> int | None:
    months = (interim_end.year - annual_end.year) * 12 + interim_end.month - annual_end.month
    if interim_end.day != monthrange(interim_end.year, interim_end.month)[1]:
        return None
    return months if 1 <= months <= 11 else None


class CSEFinancialDocumentClient:
    def __init__(self, cache_root: Path, timeout: float = 120) -> None:
        self.cache_root = cache_root / "cse_financial_announcements"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def filings(self, from_date: date, to_date: date) -> tuple[list[dict], bool]:
        cache = self.cache_root / f"{from_date.isoformat()}_{to_date.isoformat()}.json"
        if (
            cache.exists()
            and cache.stat().st_size
            and time.time() - cache.stat().st_mtime < 15 * 60
        ):
            return json.loads(cache.read_text(encoding="utf-8")), True
        response = httpx.post(
            FINANCIAL_ENDPOINT,
            data={"fromDate": from_date.isoformat(), "toDate": to_date.isoformat()},
            headers={"User-Agent": "cse-screening-research/0.4"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json().get("reqFinancialAnnouncemnets", [])
        cache.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return rows, False

    def discover(self, companies: list[dict], as_of: date) -> tuple[dict[str, list[dict]], bool]:
        try:
            start = as_of.replace(year=as_of.year - 3)
        except ValueError:
            start = as_of.replace(year=as_of.year - 3, day=28)
        filings, cached = self.filings(start, as_of)
        wanted = {item["ticker"].split(".", 1)[0] for item in companies}
        candidates: dict[str, list[dict]] = {symbol: [] for symbol in wanted}
        for row in filings:
            symbol = str(row.get("symbol") or "").upper()
            title = str(row.get("fileText") or "").strip()
            kind = filing_kind(title)
            period_end = parse_period_end(title)
            if symbol not in wanted or kind is None or period_end is None or not row.get("path"):
                continue
            publication_date = _uploaded_date(row.get("authorizedDate") or row.get("uploadedDate"))
            candidates[symbol].append(
                {
                    "kind": kind,
                    "title": title,
                    "period_end": period_end,
                    "publication_date": publication_date,
                    "url": f"https://cdn.cse.lk/{row['path']}",
                    "discovery_url": FINANCIAL_ENDPOINT,
                    "announcement_id": row.get("id"),
                }
            )
        selected_by_symbol = {
            symbol: self._latest_documents(rows) for symbol, rows in candidates.items()
        }
        results = {}
        for company in companies:
            symbol = company["ticker"].split(".", 1)[0]
            results[company["ticker"]] = [dict(item) for item in selected_by_symbol[symbol]]
        return results, cached

    @staticmethod
    def _latest_documents(rows: list[dict]) -> list[dict]:
        selected = []
        annuals = [item for item in rows if item["kind"] == "annual_report"]
        # Keep one preferred filing for each of the latest three fiscal years.
        # Comparative columns then provide an independently sourced fourth point
        # where layouts permit, while CAGR only needs three verified observations.
        annual_by_period = {}
        for item in annuals:
            key = item["period_end"]
            prior = annual_by_period.get(key)
            rank = (
                item["publication_date"] or date.min,
                "amended" in item["title"].casefold() or "updated" in item["title"].casefold(),
            )
            if prior is None or rank > (
                prior["publication_date"] or date.min,
                "amended" in prior["title"].casefold() or "updated" in prior["title"].casefold(),
            ):
                annual_by_period[key] = item
        selected.extend(annual_by_period[key] for key in sorted(annual_by_period, reverse=True)[:3])
        interims = [item for item in rows if item["kind"] == "interim_statement"]
        if interims:
            selected.append(
                max(
                    interims,
                    key=lambda item: (
                        item["period_end"],
                        item["publication_date"] or date.min,
                    ),
                )
            )
        annual = next((item for item in selected if item["kind"] == "annual_report"), None)
        interim = next((item for item in selected if item["kind"] == "interim_statement"), None)
        if annual and interim:
            months = _months_since(annual["period_end"], interim["period_end"])
            if months:
                interim["period_months"] = months
                interim["comparative_period_end"] = interim["period_end"].replace(
                    year=interim["period_end"].year - 1
                )
        return selected
