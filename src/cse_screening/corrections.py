"""Validated, persistent manual-correction overlays for extracted facts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .units import detect_unit

REQUIRED_FIELDS = {
    "id",
    "ticker",
    "metric",
    "financial_period",
    "source_document",
    "value",
    "unit",
    "source_page",
    "statement_scope",
    "reason",
    "author",
    "corrected_at",
}


def load_corrections(path: Path) -> list[dict]:
    """Load and validate an append-only correction file."""
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = payload.get("corrections", [])
    if not isinstance(items, list):
        raise TypeError(f"{path}: 'corrections' must be a list")
    seen_ids: set[str] = set()
    active_keys: set[tuple[str, str, str, str]] = set()
    validated = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise TypeError(f"{path}: correction #{index} must be a mapping")
        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise ValueError(f"{path}: correction #{index} missing {', '.join(sorted(missing))}")
        correction_id = str(item["id"])
        if correction_id in seen_ids:
            raise ValueError(f"{path}: duplicate correction id {correction_id!r}")
        seen_ids.add(correction_id)
        if item.get("status", "active") not in {"active", "superseded"}:
            raise ValueError(f"{path}: correction {correction_id!r} has invalid status")
        try:
            Decimal(str(item["value"]))
        except InvalidOperation as exc:
            raise ValueError(f"{path}: correction {correction_id!r} has invalid value") from exc
        if int(item["source_page"]) < 1:
            raise ValueError(f"{path}: correction {correction_id!r} source_page must be positive")
        key = (
            str(item["ticker"]),
            str(item["metric"]),
            str(item["financial_period"]),
            str(item["source_document"]),
        )
        if item.get("status", "active") == "active" and key in active_keys:
            raise ValueError(f"{path}: multiple active corrections target {key}")
        if item.get("status", "active") == "active":
            active_keys.add(key)
        validated.append(item)
    return validated


def correction_candidates(corrections: list[dict], ticker: str, document: dict) -> list[dict]:
    """Convert active exact-target corrections into normalized fact candidates."""
    matches = []
    for item in corrections:
        if item.get("status", "active") != "active":
            continue
        if (
            item["ticker"] != ticker
            or str(item["financial_period"]) != str(document["period_end"])
            or item["source_document"] != document["title"]
        ):
            continue
        value = Decimal(str(item["value"]))
        unit = str(item["unit"])
        if unit.casefold() in {"lkr/share", "per share", "ratio", "shares"}:
            multiplier = Decimal(1)
            normalized_unit = "LKR/share" if "share" in unit.casefold() else unit
        else:
            detected = detect_unit(unit)
            if detected is None:
                raise ValueError(f"Correction {item['id']!r} has unsupported unit {unit!r}")
            normalized_unit, multiplier = "LKR", detected[1]
        matches.append(
            {
                "metric": item["metric"],
                "value": value * multiplier,
                "original_value": value,
                "unit": normalized_unit,
                "original_unit": unit,
                "multiplier": multiplier,
                "page": int(item["source_page"]),
                "source_text": item.get("source_text", "Manual transcription from cited page"),
                "confidence": Decimal(1),
                "comparatives": [value],
                "correction_id": str(item["id"]),
                "statement_scope": item["statement_scope"],
                "notes": (
                    f"Manual correction by {item['author']} on {item['corrected_at']}: "
                    f"{item['reason']}"
                ),
            }
        )
    return matches
