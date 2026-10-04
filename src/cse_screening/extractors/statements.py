"""Conservative label-based extraction from statement pages."""

from __future__ import annotations

import re
from decimal import Decimal

from ..units import detect_unit, parse_number
from .layout import (
    locate_statements,
    normalize_text,
    strip_note_reference,
    trailing_values,
)
from .primary import PRIMARY_ROWS, extract_primary_metrics

METRIC_ALIASES = {
    "revenue": (r"^revenue(?! reserves)\b", r"^turnover\b"),
    "operating_profit": (
        r"^profit from operations\b",
        r"^operating profit\b",
        r"^results from operating activities\b",
    ),
    "ebit": (
        r"^earnings before interest (?:and|&) tax(?:\s*\(ebit\))?\b",
        r"^profit before interest (?:and|&) tax\b",
    ),
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
    "total_equity": (r"^total equity\b(?!\s*(?:and|&)\s*liabilities)",),
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


def extract_one_off_indicators(pages: list[str]) -> list[dict]:
    """Find explicit one-off/non-recurring profit or loss wording for review."""
    phrase = re.compile(
        r"\b(?:one[- ]off|non[- ]recurring)\b|"
        r"\bexceptional\s+(?:item|gain|loss|charge|income|expense)s?\b",
        re.IGNORECASE,
    )
    outcome = re.compile(r"\b(?:profit|loss|gain|earnings|income|expense|charge)\b", re.IGNORECASE)
    results = []
    for page_number, text in enumerate(pages, 1):
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            match = phrase.search(cleaned)
            if match and outcome.search(cleaned):
                start, end = max(0, match.start() - 180), min(len(cleaned), match.end() + 220)
                excerpt = cleaned[start:end]
                results.append({"page": page_number, "source_text": excerpt})
                if len(results) == 3:
                    return results
    return results


def candidate_pages(pages: list[str]) -> list[tuple[int, str]]:
    headings = (
        "statement of profit or loss",
        "income statement",
        "consolidated statement",
        "statement of financial position",
        "statement of cash flows",
        "financial highlights",
        "results from operating activities",
    )
    selected = [
        (i, text) for i, text in enumerate(pages, 1) if any(h in text.lower() for h in headings)
    ]
    selected.sort(key=lambda item: ("financial highlights" in item[1].lower(), item[0]))
    return selected or list(enumerate(pages, 1))


def _legacy_scan(pages: list[str]) -> list[dict]:
    """First label match across candidate pages; used when no statement is located."""
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
                # Read the row's amount cells as tokens so a note reference is
                # told apart from a per-share amount by how it is written (an
                # integer such as "11" versus "6.00"), not by its size alone.
                cells = strip_note_reference(trailing_values(cleaned), None)
                values = [value for value in cells.values if value is not None]
                if len(values) < 2:
                    continue
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


HIGHLIGHT_ONLY_METRICS = {"bvps", "dps", "ebit"}


def extract_metrics(
    pages: list[str], located: dict[str, list[int]] | None = None, interim: bool = False
) -> list[dict]:
    """Extract statement metrics, preferring the located primary statements.

    Rows are read from the primary income statement, statement of financial
    position and cash-flow statement when they can be located. A label match
    elsewhere in the document is kept only as a low-confidence candidate for a
    metric whose primary statement was found but has no such row, so highlights,
    segment tables and multi-year summaries cannot silently stand in for it.
    """
    pages = [normalize_text(page) for page in pages]
    if located is None:
        located = locate_statements(pages)
    primary = extract_primary_metrics(pages, located, interim) if located else []
    found = {item["metric"] for item in primary}
    results = list(primary)
    for candidate in _legacy_scan(pages):
        metric = candidate["metric"]
        if metric in found:
            continue
        statement = PRIMARY_ROWS.get(metric, (None,))[0]
        if metric == "net_profit_attributable":
            statement = "income"
        if statement in located and metric not in HIGHLIGHT_ONLY_METRICS:
            candidate["confidence"] = min(candidate["confidence"], Decimal("0.70"))
            candidate["notes"] = (
                "No matching row on the located primary statement; this is the first label "
                "match elsewhere in the document and needs review."
            )
            candidate["extraction_method"] = "label_match_outside_primary_statement"
        results.append(candidate)
        found.add(metric)
    return results


def extract_document_metrics(pages: list[str], kind: str = "annual_report") -> list[dict]:
    """All metric candidates for one document, one candidate per metric."""
    pages = [normalize_text(page) for page in pages]
    located = locate_statements(pages)
    interim = kind == "interim_statement"
    by_metric = {item["metric"]: item for item in extract_metrics(pages, located, interim)}
    threshold = Decimal("0.8")
    if interim:
        # Layouts that print audited annual columns to the left of the row label.
        for candidate in extract_interim_flow_metrics(pages):
            existing = by_metric.get(candidate["metric"])
            if existing is None or existing["confidence"] < threshold:
                candidate.setdefault("extraction_method", "interim_same_scope_columns")
                by_metric[candidate["metric"]] = candidate
    if "position" not in located:
        # Note-level fallbacks are only needed when no statement of financial
        # position was located; otherwise an absent row means it is not reported.
        fallbacks = (
            (extract_total_debt, "debt_component_aggregation"),
            (extract_cash_equivalents, "cash_component_aggregation"),
            (extract_retained_earnings_note, "retained_earnings_note"),
        )
        for extractor, method in fallbacks:
            candidate = extractor(pages)
            if candidate is None:
                continue
            existing = by_metric.get(candidate["metric"])
            if existing is None or existing["confidence"] < candidate["confidence"]:
                candidate.setdefault("extraction_method", method)
                by_metric[candidate["metric"]] = candidate
    shares = extract_ordinary_shares(pages)
    if shares is not None:
        shares.setdefault("extraction_method", "ordinary_share_count")
        by_metric[shares["metric"]] = shares
    return list(by_metric.values())


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
        period = re.search(r"\b0?([369]) months? to", header)
        if "unaudited" not in header or not period:
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
                        "period_months": int(period.group(1)),
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


def extract_ordinary_shares(pages: list[str]) -> dict | None:
    """Extract period-end ordinary shares, with weighted average as a labelled fallback."""
    primary = (
        r"^number of ordinary shares\b",
        r"^number of shares in issue",
        r"^issued ordinary shares as at",
        r"^number of ordinary shares \(voting\) issued",
    )
    fallback = (
        r"weighted average number of ordinary shares(?: in issue| outstanding)?",
        r"weighted-average number of ordinary shares",
        r"weighted average no\.?\s*of ordinary shares",
    )

    # Some reports disclose the period-end count in narrative stated-capital text,
    # with the number before the words "ordinary shares". Keep these explicit
    # patterns ahead of the weighted-average EPS denominator fallback.
    narrative_patterns = (
        r"represented by\s+([\d,]+)\s+ordinary shares",
        r"stated capital\s*\(([\d,]+)\s+shares\)",
    )
    for page_number, text in enumerate(pages, 1):
        flattened = " ".join(text.split())
        for pattern in narrative_patterns:
            match = re.search(pattern, flattened, re.IGNORECASE)
            if match and (value := parse_number(match.group(1))) is not None:
                return {
                    "metric": "ordinary_shares_outstanding",
                    "value": value,
                    "original_value": value,
                    "unit": "shares",
                    "original_unit": "shares",
                    "multiplier": Decimal(1),
                    "page": page_number,
                    "source_text": match.group(0),
                    "confidence": Decimal("0.90"),
                    "comparatives": [value],
                    "notes": "Period-end ordinary shares from stated-capital disclosure.",
                }

    for patterns, confidence, method, note in (
        (primary, Decimal("0.90"), "period_end_share_count", "Period-end ordinary shares."),
        (
            fallback,
            Decimal("0.78"),
            "weighted_average_share_count_fallback",
            "Weighted-average ordinary shares used because no period-end count was identified.",
        ),
    ):
        for page_number, text in enumerate(pages, 1):
            lines = text.splitlines()
            for index, line in enumerate(lines):
                # PDF table labels frequently wrap across two or three physical
                # lines, with the values appearing only on the final line.
                cleaned = " ".join(" ".join(lines[index : index + 3]).split())
                match = next(
                    (
                        result
                        for pattern in patterns
                        if (result := re.search(pattern, cleaned, re.IGNORECASE))
                    ),
                    None,
                )
                if match is None:
                    continue
                tail = cleaned[match.end() :]
                values = [parse_number(item) for item in NUMBER.findall(tail)]
                values = [item for item in values if item is not None]
                # Only a scale stated on the share row itself applies to it; a
                # currency scale on a neighbouring profit row does not.
                scoped = cleaned[match.start() :]
                scale_text = re.sub(
                    r"(?:rs\.?|lkr)\s*['‘’]?\s*000", "", scoped, flags=re.IGNORECASE
                )
                lowered = scale_text.casefold()
                if "million" in lowered or re.search(r"\bmn\b", lowered):
                    multiplier = Decimal(1000000)
                elif re.search(r"(?:['‘’]\s*000|no\.\s*['‘’]?000)", scale_text, re.IGNORECASE):
                    multiplier = Decimal(1000)
                else:
                    multiplier = Decimal(1)
                values = [item for item in values if item != 0]
                if multiplier == 1000 and len(values) >= 2 and abs(values[0]) <= 200:
                    values = values[1:]
                if multiplier == 1:
                    values = [item for item in values if abs(item) > 2000]
                if not values:
                    continue
                return {
                    "metric": "ordinary_shares_outstanding",
                    "value": values[0] * multiplier,
                    "original_value": values[0],
                    "unit": "shares",
                    "original_unit": "million shares"
                    if multiplier == 1000000
                    else ("shares '000" if multiplier == 1000 else "shares"),
                    "multiplier": multiplier,
                    "page": page_number,
                    "source_text": cleaned,
                    "confidence": confidence,
                    "comparatives": values,
                    "notes": note,
                }
    return None
