"""HTTP download cache and current CSE market data."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx


class CachedDownloader:
    def __init__(self, root: Path, timeout: float = 60) -> None:
        self.root = root
        self.timeout = timeout
        self.root.mkdir(parents=True, exist_ok=True)

    def download(self, ticker: str, url: str, title: str) -> tuple[Path, str, bool]:
        suffix = Path(urlparse(url).path).suffix or ".pdf"
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = self.root / ticker.replace(".", "_") / f"{key}{suffix}"
        if path.exists() and path.stat().st_size:
            return path, hashlib.sha256(path.read_bytes()).hexdigest(), True
        path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
            response = client.get(url, headers={"User-Agent": "cse-screening-research/0.1"})
            response.raise_for_status()
        content = response.content
        if not content.startswith(b"%PDF"):
            raise ValueError(
                f"Expected PDF for {title}, received {response.headers.get('content-type')}"
            )
        path.write_bytes(content)
        return path, hashlib.sha256(content).hexdigest(), False


def get_market_data(ticker: str) -> dict:
    response = httpx.post(
        "https://www.cse.lk/api/companyInfoSummery",
        data={"symbol": ticker},
        headers={"User-Agent": "cse-screening-research/0.1"},
        timeout=30,
    )
    response.raise_for_status()
    info = response.json()["reqSymbolInfo"]
    return {
        "price": info.get("lastTradedPrice") or info.get("closingPrice"),
        "market_cap": info.get("marketCap"),
        "share_volume": info.get("tdyShareVolume"),
        "trade_volume": info.get("tdyTradeVolume"),
        "quantity_issued": info.get("quantityIssued"),
        "market_source_url": "https://www.cse.lk/api/companyInfoSummery",
    }
