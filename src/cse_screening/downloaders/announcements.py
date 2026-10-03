"""Official CSE cash-dividend announcement discovery and detail caching."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .universe import CSE_API


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


class CSEDividendClient:
    def __init__(self, cache_root: Path, timeout: float = 30) -> None:
        self.cache_root = cache_root / "cse_announcements"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def _post(self, endpoint: str, data: dict | None = None) -> dict:
        response = httpx.post(
            f"{CSE_API}/{endpoint}",
            data=data,
            headers={"User-Agent": "cse-screening-research/0.3"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def latest_for_companies(self, companies: list[dict]) -> dict[str, list[dict]]:
        """Fetch the live feed once and resolve full details only for requested issuers."""
        feed = self._post("approvedAnnouncement").get("approvedAnnouncements", [])
        by_name = {_company_key(item["name"]): item["ticker"] for item in companies}
        results: dict[str, list[dict]] = {}
        for summary in feed:
            if summary.get("announcementCategory") != "CASH DIVIDEND":
                continue
            ticker = by_name.get(_company_key(summary.get("company", "")))
            if ticker is None:
                continue
            announcement_id = summary.get("announcementId")
            if announcement_id is None:
                continue
            detail, cached = self.detail(int(announcement_id))
            detail["_cache_hit"] = cached
            detail["_feed_id"] = summary.get("id")
            results.setdefault(ticker, []).append(detail)
        return results

    def detail(self, announcement_id: int) -> tuple[dict, bool]:
        path = self.cache_root / f"{announcement_id}.json"
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8")), True
        payload = self._post("getAnnouncementById", {"announcementId": announcement_id})
        payload["_retrieved_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload, False


def dividend_type(item: dict) -> str | None:
    labels = (
        ("typeFirstInt", "first interim"),
        ("typeSecondInt", "second interim"),
        ("typeThirdInt", "third interim"),
        ("typeFourthInt", "fourth interim"),
        ("typeFinalInt", "final interim"),
        ("firstAndFinal", "first and final"),
        ("finalDividend", "final"),
        ("typeOther", "other"),
    )
    return next((label for key, label in labels if item.get(key)), None)
