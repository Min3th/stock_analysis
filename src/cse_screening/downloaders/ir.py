"""Optional issuer investor-relations fallback: PDF links on the issuer's own domain.

This is a last resort for periods the CSE archive does not list. Only links on
the configured ``ir_url`` host (or its subdomains) that name a financial report
and its period are kept. Results are labelled ``issuer_ir`` and rank below every
other source in ``_merge_documents``.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from .financials import _months_since, filing_kind, parse_period_end

SOURCE_TYPE = "issuer_ir"


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


def same_site(url: str, base_url: str) -> bool:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    base = (urlparse(base_url).hostname or "").removeprefix("www.")
    return bool(host) and bool(base) and (host == base or host.endswith("." + base))


def parse_ir_page(html: str, page_url: str) -> list[dict]:
    """Financial-report PDFs linked from one IR page."""
    parser = _Links()
    parser.feed(html)
    documents: dict[str, dict] = {}
    for href, text in parser.links:
        url = urljoin(page_url, href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.path.casefold().endswith(".pdf"):
            continue
        if not same_site(url, page_url):
            continue
        filename = re.sub(r"[-_.]+", " ", Path(unquote(parsed.path)).stem)
        # The link text is the better title; the file name can supply a missing date.
        for title in (text, filename, f"{text} {filename}"):
            kind, period_end = filing_kind(title), parse_period_end(title)
            if kind and period_end:
                documents[url] = {
                    "kind": kind,
                    "title": text or filename,
                    "period_end": period_end,
                    "publication_date": None,
                    "url": url,
                    "source_type": SOURCE_TYPE,
                    "discovery_page": page_url,
                }
                break
    return list(documents.values())


def annotate_interim_periods(documents: list[dict]) -> list[dict]:
    """Give interim statements their length and comparative date from the annual year-end."""
    annuals = sorted(item["period_end"] for item in documents if item["kind"] == "annual_report")
    for item in documents:
        if item["kind"] != "interim_statement" or item.get("period_months"):
            continue
        earlier = [end for end in annuals if end < item["period_end"]]
        months = _months_since(earlier[-1], item["period_end"]) if earlier else None
        if months:
            item["period_months"] = months
            item["comparative_period_end"] = item["period_end"].replace(
                year=item["period_end"].year - 1
            )
    return documents


def discover_ir_documents(
    ir_url: str,
    ticker: str,
    cache_root: Path,
    *,
    offline: bool = False,
    timeout: float = 30,
    user_agent: str = "cse-screening-research/0.1",
) -> list[dict]:
    cache = cache_root / "issuer_ir" / f"{ticker.replace('.', '_')}.html"
    if offline:
        if not cache.exists():
            raise OSError(f"Offline mode: no cached IR page for {ticker}")
        html = cache.read_text(encoding="utf-8")
    else:
        response = httpx.get(
            ir_url, headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True
        )
        response.raise_for_status()
        html = response.text
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    return annotate_interim_periods(parse_ir_page(html, ir_url))
