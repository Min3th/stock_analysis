"""Comparable-period checks."""

from .models import FinancialPeriod, PeriodKind


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
