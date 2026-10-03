"""Comparable-period checks and conservative TTM construction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import pairwise

from .models import FinancialPeriod, PeriodKind

TTM_FLOW_METRICS = {
    "revenue",
    "operating_profit",
    "ebit",
    "net_profit",
    "net_profit_attributable",
    "operating_cash_flow",
    "capital_expenditure",
    "eps",
}


def periods_comparable(current: FinancialPeriod, previous: FinancialPeriod) -> bool:
    if current.kind == previous.kind == PeriodKind.ANNUAL:
        return True
    if current.kind != previous.kind:
        return False
    return current.months is not None and current.months == previous.months


def period_label(period: str) -> tuple[int, int | None]:
    value = period.upper().strip()
    if "Q" in value:
        year, quarter = value.split("Q", 1)
        q = int(quarter)
        if q not in range(1, 5):
            raise ValueError("Quarter must be from Q1 through Q4")
        return int(year), q
    return int(value), None


def ttm_from_annual_and_ytd(
    annual: Decimal | None,
    current_ytd: Decimal | None,
    prior_ytd: Decimal | None,
    *,
    annual_end: date,
    current_end: date,
    prior_end: date,
    months: int,
) -> Decimal | None:
    """Return FY + current YTD - prior YTD only for compatible fiscal periods."""
    if any(value is None for value in (annual, current_ytd, prior_ytd)):
        return None
    if not 1 <= months <= 11 or current_end <= annual_end:
        return None
    if (current_end.month, current_end.day) != (prior_end.month, prior_end.day):
        return None
    if current_end.year - prior_end.year != 1:
        return None
    # The prior comparative must fall inside the annual period being rolled.
    if not prior_end <= annual_end < current_end:
        return None
    return annual + current_ytd - prior_ytd


def ttm_from_quarters(quarters: list[tuple[date, Decimal, int]]) -> Decimal | None:
    """Sum exactly four consecutive, discrete three-month quarters."""
    if len(quarters) != 4 or any(months != 3 for _, _, months in quarters):
        return None
    ordered = sorted(quarters, key=lambda item: item[0])
    for previous, current in pairwise(ordered):
        month_gap = (current[0].year - previous[0].year) * 12 + current[0].month - previous[0].month
        if month_gap != 3:
            return None
    return sum((value for _, value, _ in ordered), Decimal(0))
