"""Financial-year dividends per share from official CSE cash-dividend announcements.

Each announcement names the financial year it is "for" (``financialYear``). Cash
interim and final dividends for one year are summed. A year is *complete* only
once a final (or first-and-final) dividend has been announced; a partial sum is
never presented as the year's dividend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..downloaders.announcements import dividend_type
from ..downloaders.financials import parse_period_end

NON_CASH = re.compile(r"scrip|script|bonus|rights|capitali[sz]ation|share dividend", re.IGNORECASE)
FINAL_TYPES = {"final", "first and final"}
TOLERANCE = Decimal("0.05")


@dataclass
class FinancialYearDividend:
    fy_end: date
    dps: Decimal
    complete: bool
    announcement_ids: list[int] = field(default_factory=list)
    types: list[str] = field(default_factory=list)


def is_cash_dividend(base: dict) -> bool:
    text = f"{base.get('dType') or ''} {base.get('remarks') or ''}"
    return not NON_CASH.search(text)


def announced_dps(base: dict, share_class: str) -> Decimal | None:
    """Dividend per share for the ticker's class (``N`` voting, ``X`` non-voting)."""
    key = "nonVotingDivPerShare" if share_class == "X" else "votingDivPerShare"
    for field_name in (key, "divPerShare"):
        value = base.get(field_name)
        if value not in (None, 0, "0"):
            return Decimal(str(value))
    return None


def financial_year_dividends(
    announcements: list[dict], ticker: str
) -> dict[date, FinancialYearDividend]:
    """Cash dividends per financial year end for one ticker."""
    share_class = "X" if re.search(r"\.X\d+$", ticker) else "N"
    chosen: dict[tuple[date, str], dict] = {}
    for announcement in announcements:
        base = announcement.get("reqBaseAnnouncement", announcement)
        label = dividend_type(base)
        fy_end = parse_period_end(str(base.get("financialYear") or ""))
        if label is None or label == "other" or fy_end is None or not is_cash_dividend(base):
            continue
        if announced_dps(base, share_class) is None:
            continue
        key = (fy_end, label)
        # An amended announcement for the same dividend replaces the earlier one.
        if key not in chosen or int(base.get("id") or 0) > int(chosen[key].get("id") or 0):
            chosen[key] = base
    years: dict[date, FinancialYearDividend] = {}
    for (fy_end, label), base in sorted(chosen.items(), key=lambda item: item[0][0]):
        year = years.setdefault(fy_end, FinancialYearDividend(fy_end, Decimal(0), False))
        year.dps += announced_dps(base, share_class)
        year.announcement_ids.append(int(base["id"]))
        year.types.append(label)
        year.complete = year.complete or label in FINAL_TYPES
    return years


def dps_conflict(statement: Decimal, announced: Decimal) -> bool:
    """True when the statement DPS and the announced total differ materially."""
    if statement == announced:
        return False
    reference = max(abs(statement), abs(announced))
    return abs(statement - announced) > reference * TOLERANCE
