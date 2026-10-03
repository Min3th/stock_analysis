"""Conservative label-based extraction from statement pages."""

from __future__ import annotations

import re
from decimal import Decimal

from ..units import detect_unit, parse_number

METRIC_ALIASES = {
    "revenue": (r"^revenue\b", r"^turnover\b"),
    "operating_profit": (r"^profit from operations\b", r"^operating profit\b"),
    "net_profit": (r"^profit for the year\b", r"^profit for the period\b"),
    "net_profit_attributable": (r"^owners of the parent\b", r"^equity holders of the parent\b"),
    "total_assets": (r"^total assets\b",),
    "total_liabilities": (r"^total liabilities\b",),
    "total_equity": (r"^total equity\b",),
    "cash": (r"^cash and cash equivalents\b",),
    "operating_cash_flow": (r"^net cash (?:generated from|flows? from) operating activities\b",),
    "eps": (r"^earnings per share\b", r"^basic earnings per share\b"),
    "bvps": (r"^net assets? per share\b", r"^book value per share\b"),
    "dps": (r"^dividend per share\b",),
}

NUMBER = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")


def candidate_pages(pages: list[str]) -> list[tuple[int, str]]:
    headings = (
        "statement of profit or loss",
        "income statement",
        "consolidated statement",
        "statement of financial position",
        "statement of cash flows",
        "financial highlights",
    )
    selected = [
        (i, text) for i, text in enumerate(pages, 1) if any(h in text.lower() for h in headings)
    ]
    return selected or list(enumerate(pages, 1))


def extract_metrics(pages: list[str]) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for page_number, text in candidate_pages(pages):
        unit = detect_unit(text[:2000])
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            for metric, aliases in METRIC_ALIASES.items():
                if metric in seen or not any(
                    re.search(alias, cleaned, re.IGNORECASE) for alias in aliases
                ):
                    continue
                matches = NUMBER.findall(cleaned)
                values = [parse_number(match) for match in matches]
                values = [value for value in values if value is not None]
                if len(values) < 2:
                    continue
                # Audited statements commonly place a small note reference before
                # the current-period amount. Do not mistake that reference for data.
                has_note_reference = (
                    values[0] == values[0].to_integral_value()
                    and abs(values[0]) <= 200
                    and abs(values[1]) > 200
                )
                per_share_note = (
                    metric in {"eps", "bvps", "dps"}
                    and values[0] == values[0].to_integral_value()
                    and abs(values[0]) <= 200
                    and (
                        (metric == "eps" and len(values) >= 5)
                        or abs(values[0]) > abs(values[1]) * 3
                    )
                )
                if has_note_reference or per_share_note:
                    values = values[1:]
                value: Decimal = values[0]
                is_per_share = metric in {"eps", "bvps", "dps"}
                multiplier = Decimal(1) if is_per_share else (unit[1] if unit else Decimal(1))
                # A value already in the billions cannot plausibly be an LKR '000
                # presentation for this issuer universe; page-level footnotes can
                # otherwise leak a secondary unit marker into the statement page.
                if not is_per_share and abs(value) >= Decimal(1000000000):
                    multiplier = Decimal(1)
                results.append(
                    {
                        "metric": metric,
                        "value": value * multiplier,
                        "original_value": value,
                        "unit": "LKR/share" if is_per_share else "LKR",
                        "original_unit": "LKR/share"
                        if is_per_share
                        else (unit[0] if unit else "unknown"),
                        "multiplier": multiplier,
                        "page": page_number,
                        "source_text": cleaned,
                        "confidence": Decimal("0.82") if unit or is_per_share else Decimal("0.62"),
                        "comparatives": values,
                    }
                )
                seen.add(metric)
    return results
