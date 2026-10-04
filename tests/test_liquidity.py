import json
from datetime import UTC, datetime
from decimal import Decimal as D

from cse_screening.downloaders.liquidity import LiquidityStore


def _company(volume: int, timestamp: datetime) -> dict:
    return {
        "ticker": "TEST.N0000",
        "market_data": {
            "share_volume": volume,
            "trade_volume": 5,
            "turnover": 1000,
            "last_traded_time": int(timestamp.timestamp() * 1000),
            "market_source_url": "https://www.cse.lk/api/gics_sector_companies",
        },
    }


def test_liquidity_capture_upserts_same_trading_day(tmp_path):
    store = LiquidityStore(tmp_path)
    timestamp = datetime(2026, 10, 2, 8, tzinfo=UTC)
    store.capture([_company(100, timestamp)])
    store.capture([_company(250, timestamp)])
    files = list((tmp_path / "market_liquidity").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["TEST.N0000"]["share_volume"] == 250


def test_liquidity_summary_uses_latest_trading_day_observations(tmp_path):
    root = tmp_path / "market_liquidity"
    root.mkdir()
    for day, volume in (("2026-10-01", 100), ("2026-10-02", 300), ("2026-10-03", 500)):
        (root / f"{day}.json").write_text(
            json.dumps(
                {
                    "TEST.N0000": {
                        "ticker": "TEST.N0000",
                        "trading_date": day,
                        "share_volume": volume,
                        "source_url": "https://www.cse.lk/api/gics_sector_companies",
                    }
                }
            ),
            encoding="utf-8",
        )
    summary = LiquidityStore(tmp_path).summaries(["TEST.N0000"], 2)["TEST.N0000"]
    assert summary["average_volume"] == D(400)
    assert summary["median_volume"] == D(400)
    assert summary["observations"] == 2
    assert summary["period_start"] == "2026-10-02"
    assert summary["period_end"] == "2026-10-03"
