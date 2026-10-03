"""Conservative label-based extraction from statement pages."""

from __future__ import annotations

import re
from decimal import Decimal

from ..units import detect_unit, parse_number

METRIC_ALIASES = {
    "revenue": (r"^revenue\b", r"^turnover\b"),
    "operating_profit": (r"^profit from operations\b", r"^operating profit\b"),
    "net_profit": (
        r"^profit for the year\b",
        r"^profit for the period\b",
        r"^profit/?\s*(?:\(loss\))?\s*for the year\b",
    ),
    "net_profit_attributable": (
        r"^-?\s*owners of (?:the )?(?:parent|company)\b",
        r"^equity holders of the parent\b",
    ),
    "total_assets": (r"^total assets\b",),
    "total_liabilities": (r"^total liabilities\b",),
    "total_equity": (r"^total equity\b",),
    "ordinary_equity": (
        r"^equity attributable to (?:owners|equity holders) of the (?:company|parent)\b",
        r"^total equity attributable to equity holders of the company\b",
    ),
    "cash": (r"^cash and cash equivalents\b",),
    "operating_cash_flow": (
        r"^net cash (?:generated from|flows? from) operating activities\b",
        r"^net cash (?:inflow|outflow) from operating activities\b",
    ),
    "capital_expenditure": (
        r"^purchase (?:and construction )?of property, plant (?:and|&) equipment\b",
    ),
    "retained_earnings": (r"^retained earnings\b",),
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
    selected.sort(key=lambda item: ("financial highlights" in item[1].lower(), item[0]))
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
                inline_unit = detect_unit(cleaned)
                selected_unit = inline_unit or unit
                multiplier = (
                    Decimal(1)
                    if is_per_share
                    else (selected_unit[1] if selected_unit else Decimal(1))
                )
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
                        else (selected_unit[0] if selected_unit else "unknown"),
                        "multiplier": multiplier,
                        "page": page_number,
                        "source_text": cleaned,
                        "confidence": Decimal("0.82")
                        if selected_unit or is_per_share
                        else Decimal("0.62"),
                        "comparatives": values,
                    }
                )
                seen.add(metric)
        if "operating_cash_flow" not in seen:
            flat = " ".join(text.split())
            match = re.search(
                r"net cash (?:flows? )?(?:generated from|inflow from|outflow from|used in)\s*/?\s*"
                r"(?:\(used in\) )?operating activities\s+"
                r"(\(?-?[\d,]+(?:\.\d+)?\)?)\s+(\(?-?[\d,]+(?:\.\d+)?\)?)",
                flat,
                re.IGNORECASE,
            )
            if match:
                values = [parse_number(match.group(1)), parse_number(match.group(2))]
                multiplier = unit[1] if unit else Decimal(1)
                if abs(values[0]) >= Decimal(1000000000):
                    multiplier = Decimal(1)
                results.append(
                    {
                        "metric": "operating_cash_flow",
                        "value": values[0] * multiplier,
                        "original_value": values[0],
                        "unit": "LKR",
                        "original_unit": unit[0] if unit else "LKR",
                        "multiplier": multiplier,
                        "page": page_number,
                        "source_text": match.group(0),
                        "confidence": Decimal("0.90") if unit else Decimal("0.82"),
                        "comparatives": values,
                    }
                )
                seen.add("operating_cash_flow")
        if "ordinary_equity" not in seen:
            flat = " ".join(text.split())
            match = re.search(
                r"equity attributable to equity holders of (?:the )?parent\s+"
                r"(\(?-?[\d,]+(?:\.\d+)?\)?)\s+(\(?-?[\d,]+(?:\.\d+)?\)?)",
                flat,
                re.IGNORECASE,
            )
            if match:
                values = [parse_number(match.group(1)), parse_number(match.group(2))]
                multiplier = unit[1] if unit else Decimal(1)
                if abs(values[0]) >= Decimal(1000000000):
                    multiplier = Decimal(1)
                results.append(
                    {
                        "metric": "ordinary_equity",
                        "value": values[0] * multiplier,
                        "original_value": values[0],
                        "unit": "LKR",
                        "original_unit": unit[0] if unit else "LKR",
                        "multiplier": multiplier,
                        "page": page_number,
                        "source_text": match.group(0),
                        "confidence": Decimal("0.90"),
                        "comparatives": values,
                    }
                )
                seen.add("ordinary_equity")
    return results


def extract_interim_flow_metrics(pages: list[str]) -> list[dict]:
    """Read same-scope current/prior YTD columns from interim primary statements."""
    aliases = {
        "revenue": r"\brevenue\b",
        "operating_profit": r"\b(?:results from operating activities|operating profit)\b",
        "net_profit": r"\bprofit/?\s*\(?loss\)? for the period\b",
        "net_profit_attributable": r"\bowners of (?:the )?parent\b",
        "operating_cash_flow": r"\bnet cash (?:flows? )?(?:generated from|inflow from|used in) operating activities\b",
        "capital_expenditure": r"\bpurchase (?:and construction )?of property, plant (?:and|&) equipment\b",
    }
    results = []
    seen = set()
    for page_number, text in enumerate(pages, 1):
        header = text[:1800].lower()
        if "unaudited" not in header or not re.search(r"(?:3|03|6|06|9|09) months? to", header):
            continue
        unit = detect_unit(text[:2000])
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            for metric, alias in aliases.items():
                if metric in seen:
                    continue
                match = re.search(alias, cleaned, re.IGNORECASE)
                if not match:
                    continue
                values = [parse_number(item) for item in NUMBER.findall(cleaned[match.end() :])]
                values = [value for value in values if value is not None]
                if (
                    len(values) >= 3
                    and values[0] == values[0].to_integral_value()
                    and abs(values[0]) <= 200
                ):
                    values = values[1:]
                if len(values) < 2:
                    continue
                multiplier = unit[1] if unit else Decimal(1)
                results.append(
                    {
                        "metric": metric,
                        "value": values[0] * multiplier,
                        "original_value": values[0],
                        "unit": "LKR",
                        "original_unit": unit[0] if unit else "unknown",
                        "multiplier": multiplier,
                        "page": page_number,
                        "source_text": cleaned,
                        "confidence": Decimal("0.9") if unit else Decimal("0.72"),
                        "comparatives": values[:2],
                        "notes": "Interim primary statement; current/prior same-scope columns after row label.",
                    }
                )
                seen.add(metric)
    return results


DEBT_LABELS = (
    re.compile(
        r"^(?:loans and borrowings|borrowings|interest[- ]bearing borrowings)\b", re.IGNORECASE
    ),
    re.compile(r"^current portion of long term interest[- ]bearing borrowings\b", re.IGNORECASE),
    re.compile(r"^short[- ]term interest[- ]bearing borrowings\b", re.IGNORECASE),
)


def extract_total_debt(pages: list[str]) -> dict | None:
    """Aggregate non-overlapping interest-bearing debt rows from the position statement."""
    for page_number, text in enumerate(pages, 1):
        lowered = text.lower()
        if "current liabilities" not in lowered or "total liabilities" not in lowered:
            continue
        unit = detect_unit(text[:2000])
        components = []
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            if not any(pattern.search(cleaned) for pattern in DEBT_LABELS):
                continue
            values = [parse_number(item) for item in NUMBER.findall(cleaned)]
            values = [item for item in values if item is not None]
            if len(values) < 2:
                continue
            if values[0] == values[0].to_integral_value() and abs(values[0]) <= 200:
                values = values[1:]
            multiplier = unit[1] if unit else Decimal(1)
            if abs(values[0]) >= Decimal(1000000000):
                multiplier = Decimal(1)
            components.append((cleaned, values[0] * multiplier, values[1] * multiplier))
        if components:
            current = sum(item[1] for item in components)
            previous = sum(item[2] for item in components)
            return {
                "metric": "total_debt",
                "value": current,
                "original_value": current,
                "unit": "LKR",
                "original_unit": unit[0] if unit else "LKR",
                "multiplier": Decimal(1),
                "page": page_number,
                "source_text": " | ".join(item[0] for item in components),
                "confidence": Decimal("0.90") if unit else Decimal("0.82"),
                "comparatives": [current, previous],
                "notes": "Sum of non-current, current-portion, and short-term interest-bearing borrowings; leases excluded.",
            }
    return None


def extract_cash_equivalents(pages: list[str]) -> dict | None:
    """Extract cash or aggregate the cash-flow definition of cash equivalents."""
    for page_number, text in enumerate(pages, 1):
        lowered = text.lower()
        if "total assets" not in lowered or "current assets" not in lowered:
            continue
        unit = detect_unit(text[:2000])
        components = []
        for label in (r"^short term deposits\b", r"^cash in hand and at bank\b"):
            for line in text.splitlines():
                cleaned = " ".join(line.split())
                if not re.search(label, cleaned, re.IGNORECASE):
                    continue
                values = [parse_number(item) for item in NUMBER.findall(cleaned)]
                values = [item for item in values if item is not None]
                if len(values) >= 2:
                    components.append((cleaned, values[0], values[1]))
                    break
        if len(components) == 2:
            multiplier = unit[1] if unit else Decimal(1)
            return {
                "metric": "cash",
                "value": sum(x[1] for x in components) * multiplier,
                "original_value": sum(x[1] for x in components),
                "unit": "LKR",
                "original_unit": unit[0] if unit else "LKR",
                "multiplier": multiplier,
                "page": page_number,
                "source_text": " | ".join(x[0] for x in components),
                "confidence": Decimal("0.90"),
                "comparatives": [sum(x[1] for x in components), sum(x[2] for x in components)],
                "notes": "Cash in hand and at bank plus short-term deposits, matching the report's cash-equivalent analysis.",
            }
    return None


def extract_retained_earnings_note(pages: list[str]) -> dict | None:
    for page_number, text in enumerate(pages, 1):
        if not re.search(r"23\.1\.3\s+retained earnings", text, re.IGNORECASE) or (
            "balance as at the end of the year" not in text.lower()
        ):
            continue
        unit = detect_unit(text[:2000])
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            if not re.search(r"^balance as at the end of the year\b", cleaned, re.IGNORECASE):
                continue
            values = [parse_number(item) for item in NUMBER.findall(cleaned)]
            values = [item for item in values if item is not None]
            if len(values) >= 2:
                multiplier = unit[1] if unit else Decimal(1)
                return {
                    "metric": "retained_earnings",
                    "value": values[0] * multiplier,
                    "original_value": values[0],
                    "unit": "LKR",
                    "original_unit": unit[0] if unit else "LKR",
                    "multiplier": multiplier,
                    "page": page_number,
                    "source_text": cleaned,
                    "confidence": Decimal("0.92"),
                    "comparatives": values,
                    "notes": "Closing retained earnings from the dedicated equity note.",
                }
    return None
