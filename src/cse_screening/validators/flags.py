"""Screening anomaly flags without recommendations or scores."""

from decimal import Decimal


def company_flags(row: dict, thresholds: dict) -> list[str]:
    flags: list[str] = []
    if row.get("EPS") is not None and row["EPS"] < 0:
        flags.append("negative EPS")
    if row.get("Operating Cash Flow") is not None and row["Operating Cash Flow"] < 0:
        flags.append("negative operating cash flow")
    if row.get("Debt-to-Equity") is not None and row["Debt-to-Equity"] > thresholds.get(
        "high_debt_to_equity", 2
    ):
        flags.append("high debt-to-equity")
    if row.get("Payout Ratio") is not None and row["Payout Ratio"] > 1:
        flags.append("dividend payout above 100%")
    if row.get("OCF / Net Profit") is not None and row["OCF / Net Profit"] < Decimal(
        str(thresholds.get("ocf_to_net_profit_low", 0.7))
    ):
        flags.append("operating cash flow materially below net profit")
    if row.get("Total Equity") is not None and row["Total Equity"] < 0:
        flags.append("negative equity")
    if row.get("Recent Volume") in {None, 0}:
        flags.append("low or unavailable trading liquidity")
    return flags
