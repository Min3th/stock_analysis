"""Descriptive screening anomalies without recommendations or scores."""

from __future__ import annotations

from decimal import Decimal
from statistics import median


def _threshold(settings: dict, name: str, default: str) -> Decimal:
    return Decimal(str(settings.get(name, default)))


def consecutive_decline(history: list[dict], ticker: str, metric: str) -> bool:
    """Return true only when the latest three distinct annual values decline twice."""
    observations = {
        str(item["Financial Year End"]): item["Value"]
        for item in history
        if item["Ticker"] == ticker and item["Metric"] == metric
    }
    ordered = sorted(observations.items(), reverse=True)
    if len(ordered) < 3:
        return False
    latest = ordered[:3]
    years = [int(period[:4]) for period, _ in latest]
    month_days = [period[4:] for period, _ in latest]
    if years[0] - years[1] != 1 or years[1] - years[2] != 1 or len(set(month_days)) != 1:
        return False
    return latest[0][1] < latest[1][1] < latest[2][1]


def company_flags(
    row: dict,
    thresholds: dict,
    *,
    history: list[dict] | None = None,
    total_equity: Decimal | None = None,
    one_off_evidence: list[dict] | None = None,
) -> list[str]:
    flags: list[str] = []
    if row.get("EPS") is not None and row["EPS"] < 0:
        flags.append("negative EPS")
    if history and consecutive_decline(history, row["Ticker"], "eps"):
        flags.append("declining EPS for 2+ consecutive years")
    if history and consecutive_decline(history, row["Ticker"], "revenue"):
        flags.append("declining revenue for 2+ consecutive years")
    if row.get("Operating Cash Flow") is not None and row["Operating Cash Flow"] < 0:
        flags.append("negative operating cash flow")
    if row.get("Debt-to-Equity") is not None and row["Debt-to-Equity"] > _threshold(
        thresholds, "high_debt_to_equity", "2"
    ):
        flags.append("high debt-to-equity")
    net_profit = row.get("Net Profit")
    if (
        net_profit is not None
        and net_profit > 0
        and row.get("OCF / Net Profit") is not None
        and row["OCF / Net Profit"] < _threshold(thresholds, "ocf_to_net_profit_low", "0.7")
    ):
        flags.append("operating cash flow materially below net profit")
    if total_equity is not None and total_equity < 0:
        flags.append("negative equity")
    if row.get("Payout Ratio") is not None and row["Payout Ratio"] > 1:
        flags.append("dividend payout above 100%")
    volume = row.get("Recent Volume")
    if volume is None:
        flags.append("trading liquidity unavailable")
    elif Decimal(str(volume)) <= _threshold(thresholds, "low_liquidity_daily_volume", "10000"):
        flags.append("low trading liquidity (current-volume snapshot)")
    if one_off_evidence:
        flags.append("possible one-off profit or loss")
    return flags


def sector_relative_flags(rows: list[dict], thresholds: dict) -> dict[str, list[str]]:
    """Flag valuation outliers relative to medians of positive, defined ratios."""

    def positive_values(metric: str) -> list[Decimal]:
        return [
            Decimal(str(row[metric]))
            for row in rows
            if row.get(metric) is not None and Decimal(str(row[metric])) > 0
        ]

    pe_values, pb_values = positive_values("P/E"), positive_values("P/B")
    pe_median = median(pe_values) if pe_values else None
    pb_median = median(pb_values) if pb_values else None
    output: dict[str, list[str]] = {row["Ticker"]: [] for row in rows}
    for row in rows:
        pe, pb = row.get("P/E"), row.get("P/B")
        if (
            pe_median is not None
            and pe is not None
            and pe > 0
            and Decimal(str(pe))
            > pe_median * _threshold(thresholds, "pe_sector_median_multiple", "2")
        ):
            output[row["Ticker"]].append("P/E unusually high relative to sector median")
        if pb_median is not None and pb is not None and pb > 0:
            value = Decimal(str(pb))
            if value > pb_median * _threshold(thresholds, "pb_sector_median_high_multiple", "2"):
                output[row["Ticker"]].append("P/B unusually high relative to sector median")
            elif value < pb_median * _threshold(thresholds, "pb_sector_median_low_multiple", "0.5"):
                output[row["Ticker"]].append("P/B unusually low relative to sector median")
    return output
