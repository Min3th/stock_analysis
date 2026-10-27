"""Single-document extraction preview, used to check an upload before it is accepted."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from .extractors.layout import locate_statements, normalize_text
from .extractors.statements import extract_document_metrics
from .parsers.pdf import extract_document
from .validators.extraction import validate_extracted_facts


def extract_preview(
    pdf: Path,
    kind: str,
    period_end: date,
    settings: dict | None = None,
    threshold: Decimal = Decimal("0.8"),
) -> dict:
    """Extract and validate one PDF without running the pipeline.

    Nothing here reaches the screening table; it only shows what the extractors
    would read, with page citations, so a reviewer can accept or discard it.
    """
    if kind not in {"annual_report", "interim_statement"}:
        raise ValueError("kind must be annual_report or interim_statement")
    parsed = extract_document(pdf, settings)
    facts = extract_document_metrics(parsed.pages, kind)
    issues = validate_extracted_facts(facts, implied_shares=None, multi_class=False)
    located = locate_statements([normalize_text(page) for page in parsed.pages])
    return {
        "file": pdf.name,
        "kind": kind,
        "period_end": period_end.isoformat(),
        "pages": len(parsed.pages),
        "parsing_methods": sorted(set(parsed.methods)),
        "parser_warnings": parsed.warnings,
        "located_statements": {name: _json_safe(value) for name, value in dict(located).items()},
        "facts": [
            {
                "metric": fact["metric"],
                "value": fact["value"],
                "unit": fact["unit"],
                "original_value": fact["original_value"],
                "original_unit": fact["original_unit"],
                "page": fact["page"],
                "source_text": fact["source_text"],
                "statement_scope": fact.get("statement_scope", "unknown"),
                "confidence": fact["confidence"],
                "below_threshold": fact["confidence"] < threshold,
                "extraction_method": fact.get("extraction_method", "unknown"),
                "validation_status": fact.get("validation_status", "not_run"),
                "validation_notes": fact.get("validation_notes", ""),
            }
            for fact in facts
        ],
        "validation_issues": [_json_safe(issue) for issue in issues],
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    return str(value)
