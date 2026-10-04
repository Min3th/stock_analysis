"""Persistent official CSE daily-volume snapshots and rolling liquidity measures."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo


class LiquidityStore:
    def __init__(self, raw_root: Path) -> None:
        self.root = raw_root / "market_liquidity"
        self.root.mkdir(parents=True, exist_ok=True)

    def capture(self, companies: list[dict]) -> date:
        """Upsert one observation per ticker for the CSE trading date in the response."""
        observed_on = self._observation_date(companies)
        path = self.root / f"{observed_on.isoformat()}.json"
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for company in companies:
            market = company.get("market_data") or {}
            volume = market.get("share_volume")
            payload[company["ticker"]] = {
                "ticker": company["ticker"],
                "trading_date": observed_on.isoformat(),
                "share_volume": volume,
                "trade_count": market.get("trade_volume"),
                "turnover": market.get("turnover"),
                "source_url": market.get("market_source_url"),
                "captured_utc": datetime.now(UTC).isoformat(),
            }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return observed_on

    def summaries(self, tickers: list[str], lookback: int) -> dict[str, dict]:
        observations: dict[str, list[dict]] = {ticker: [] for ticker in tickers}
        for path in sorted(self.root.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for ticker in tickers:
                item = payload.get(ticker)
                if item is not None and item.get("share_volume") is not None:
                    observations[ticker].append(item)
        output = {}
        for ticker, items in observations.items():
            selected = items[:lookback]
            volumes = [Decimal(str(item["share_volume"])) for item in selected]
            output[ticker] = {
                "average_volume": sum(volumes) / Decimal(len(volumes)) if volumes else None,
                "median_volume": median(volumes) if volumes else None,
                "observations": len(volumes),
                "lookback": lookback,
                "period_start": selected[-1]["trading_date"] if selected else None,
                "period_end": selected[0]["trading_date"] if selected else None,
                "source_url": selected[0].get("source_url") if selected else None,
            }
        return output

    @staticmethod
    def _observation_date(companies: list[dict]) -> date:
        timestamps = []
        for company in companies:
            value = (company.get("market_data") or {}).get("last_traded_time")
            if value is None:
                continue
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000
            timestamps.append(
                datetime.fromtimestamp(numeric, tz=UTC).astimezone(ZoneInfo("Asia/Colombo")).date()
            )
        return max(timestamps) if timestamps else datetime.now(ZoneInfo("Asia/Colombo")).date()
