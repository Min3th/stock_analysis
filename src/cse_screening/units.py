"""Reported-unit detection and exact normalization."""

import re
from decimal import Decimal

UNIT_PATTERNS = (
    (
        re.compile(r"(?:sri\s+lanka\s+)?rupees?\s+(?:in\s+)?thousands?", re.IGNORECASE),
        "LKR '000",
        Decimal(1000),
    ),
    (
        re.compile(r"(?:(?:rs\.?|lkr)\s*(?:in\s*)?)?[\'‘’]?000(?:s)?\b", re.IGNORECASE),
        "LKR '000",
        Decimal(1000),
    ),
    (
        re.compile(r"(?:rs\.?|lkr)\s*(?:in\s*)?(?:mn|million)", re.IGNORECASE),
        "LKR million",
        Decimal(1000000),
    ),
    (
        re.compile(r"(?:rs\.?|lkr)\s*(?:in\s*)?(?:bn|billion)", re.IGNORECASE),
        "LKR billion",
        Decimal(1000000000),
    ),
    (
        re.compile(r"\b(?:rs(?:\.)?|lkr)(?=\s|$|['0-9])", re.IGNORECASE),
        "LKR",
        Decimal(1),
    ),
)


def detect_unit(text: str) -> tuple[str, Decimal] | None:
    # Prefer explicit million/billion declarations over generic '000 text that
    # may occur elsewhere on a dense report page.
    for index in (0, 2, 3, 1, 4):
        pattern, unit, multiplier = UNIT_PATTERNS[index]
        if pattern.search(text):
            return unit, multiplier
    return None


def normalize_monetary(value: Decimal | None, unit_text: str) -> Decimal | None:
    if value is None:
        return None
    detected = detect_unit(unit_text)
    if detected is None:
        raise ValueError(f"Unrecognized monetary unit: {unit_text!r}")
    return value * detected[1]


def parse_number(text: str) -> Decimal | None:
    value = text.strip().replace(",", "").replace(" ", "")
    if value in {"", "-", "—", "–", "N/A", "NA"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1]
    value = re.sub(r"[^0-9.\-]", "", value)
    if not value or value in {"-", "."}:
        return None
    result = Decimal(value)
    return -result if negative else result
