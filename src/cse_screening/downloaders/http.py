"""HTTP download cache and current CSE market data."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

DEFAULT_USER_AGENT = "cse-screening-research/0.1"


class CachedDownloader:
    def __init__(
        self,
        root: Path,
        timeout: float = 60,
        user_agent: str = DEFAULT_USER_AGENT,
        delay: float = 0.0,
        offline: bool = False,
    ) -> None:
        self.root = root
        self.timeout = timeout
        self.user_agent = user_agent
        self.delay = delay
        self.offline = offline
        self.root.mkdir(parents=True, exist_ok=True)

    def download(self, ticker: str, url: str, title: str) -> tuple[Path, str, bool]:
        suffix = Path(urlparse(url).path).suffix or ".pdf"
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = self.root / ticker.replace(".", "_") / f"{key}{suffix}"
        if path.exists() and path.stat().st_size:
            return path, hashlib.sha256(path.read_bytes()).hexdigest(), True
        if self.offline:
            raise OSError(f"Offline mode: {title} is not in the local cache")
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.delay:
            time.sleep(self.delay)
        with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
            response = client.get(url, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
        content = response.content
        if not content.startswith(b"%PDF"):
            raise ValueError(
                f"Expected PDF for {title}, received {response.headers.get('content-type')}"
            )
        path.write_bytes(content)
        return path, hashlib.sha256(content).hexdigest(), False


def get_market_data(
    ticker: str,
    cache_root: Path | None = None,
    offline: bool = False,
    timeout: float = 30,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict:
    """Current CSE market data; snapshots are kept per day under ``market/``."""
    market_root = cache_root / "market" if cache_root is not None else None
    if offline:
        for path in sorted(market_root.glob("*.json"), reverse=True) if market_root else []:
            snapshot = json.loads(path.read_text(encoding="utf-8")).get(ticker)
            if snapshot is not None:
                return snapshot
        raise OSError(f"Offline mode: no cached market data for {ticker}")
    response = httpx.post(
        "https://www.cse.lk/api/companyInfoSummery",
        data={"symbol": ticker},
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    info = response.json()["reqSymbolInfo"]
    market = {
        "price": info.get("lastTradedPrice") or info.get("closingPrice"),
        "market_cap": info.get("marketCap"),
        "share_volume": info.get("tdyShareVolume"),
        "trade_volume": info.get("tdyTradeVolume"),
        "quantity_issued": info.get("quantityIssued"),
        "market_source_url": "https://www.cse.lk/api/companyInfoSummery",
    }
    if market_root is not None:
        market_root.mkdir(parents=True, exist_ok=True)
        path = market_root / f"{datetime.now(UTC).date().isoformat()}.json"
        snapshots = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        snapshots[ticker] = market
        path.write_text(json.dumps(snapshots, indent=2, default=str), encoding="utf-8")
    return market
