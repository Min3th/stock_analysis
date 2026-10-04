"""Page-preserving native text, table, and OCR extraction."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf

CACHE_VERSION = 2
STATEMENT_TERMS = (
    "statement of profit or loss",
    "statement of financial position",
    "statement of cash flows",
    "income statement",
    "earnings per share",
)


@dataclass
class ParsedDocument:
    pages: list[str]
    methods: list[str]
    warnings: list[dict]


class OCRUnavailable(RuntimeError):
    pass


def extract_document(path: Path, settings: dict | None = None) -> ParsedDocument:
    settings = settings or {}
    ocr = settings.get("ocr", {})
    tables = settings.get("tables", {})
    minimum = int(ocr.get("minimum_text_characters_per_page", 80))
    cache = path.with_suffix(f"{path.suffix}.pages.v{CACHE_VERSION}.json")
    cache_key = {
        "ocr_enabled": bool(ocr.get("enabled", False)),
        "minimum_text_characters_per_page": minimum,
        "table_enabled": bool(tables.get("enabled", True)),
    }
    if cache.exists() and cache.stat().st_size:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if payload.get("version") == CACHE_VERSION and payload.get("settings") == cache_key:
            warnings = _filter_cached_ocr_warnings(
                payload["pages"], payload.get("warnings", []), minimum
            )
            has_pending_ocr = any(item.get("strategy") == "ocr" for item in warnings)
            if not (has_pending_ocr and _ocr_runtime_available()):
                if warnings != payload.get("warnings", []):
                    payload["warnings"] = warnings
                    cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return ParsedDocument(payload["pages"], payload["methods"], warnings)

    pages, methods, warnings = [], [], []
    with pymupdf.open(path) as document:
        native_pages = [page.get_text("text", sort=True).strip() for page in document]
        image_counts = [len(page.get_images(full=True)) for page in document]
        ocr_pages = _ocr_candidate_pages(native_pages, image_counts, minimum)
        for page_number, page in enumerate(document, 1):
            native = native_pages[page_number - 1]
            parts = [native] if native else []
            used = ["native_text"] if native else []
            if cache_key["table_enabled"] and _needs_table_extraction(native):
                try:
                    table_text = _extract_tables(page)
                except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                    warnings.append(
                        {
                            "page": page_number,
                            "strategy": "pymupdf_table",
                            "reason": f"Table extraction failed: {exc}",
                        }
                    )
                else:
                    if table_text and table_text not in native:
                        parts.append(table_text)
                        used.append("pymupdf_table")
            if page_number in ocr_pages and ocr.get("enabled", False):
                try:
                    ocr_text = _ocr_page(page, int(ocr.get("dpi", 300)))
                except OCRUnavailable as exc:
                    warnings.append({"page": page_number, "strategy": "ocr", "reason": str(exc)})
                else:
                    if ocr_text:
                        parts.append(ocr_text)
                        used.append("ocr_tesseract")
                    else:
                        warnings.append(
                            {
                                "page": page_number,
                                "strategy": "ocr",
                                "reason": "OCR completed but returned no text.",
                            }
                        )
            pages.append("\n".join(parts))
            methods.append("+".join(used) if used else "no_text")
    payload = {
        "version": CACHE_VERSION,
        "settings": cache_key,
        "pages": pages,
        "methods": methods,
        "warnings": warnings,
    }
    cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return ParsedDocument(pages, methods, warnings)


def extract_pages(path: Path) -> list[str]:
    """Compatibility wrapper for callers that only need page text."""
    return extract_document(path).pages


def _needs_table_extraction(text: str) -> bool:
    lowered = text.casefold()
    return bool(text) and (len(text) < 1200 or any(term in lowered for term in STATEMENT_TERMS))


def _needs_ocr(text: str, image_count: int, minimum: int) -> bool:
    return len("".join(text.split())) < minimum and image_count > 0


def _ocr_candidate_pages(
    native_pages: list[str], image_counts: list[int], minimum: int
) -> set[int]:
    candidates = {
        index + 1
        for index, (text, images) in enumerate(zip(native_pages, image_counts, strict=True))
        if _needs_ocr(text, images, minimum)
    }
    if not candidates:
        return set()
    candidate_ratio = len(candidates) / len(native_pages)
    if candidate_ratio >= 0.75 or (len(candidates) >= 3 and candidate_ratio >= 0.25):
        return candidates
    selected = set()
    for page_number in candidates:
        nearby = native_pages[max(0, page_number - 2) : min(len(native_pages), page_number + 1)]
        if any(any(term in text.casefold() for term in STATEMENT_TERMS) for text in nearby):
            selected.add(page_number)
    return selected


def _filter_cached_ocr_warnings(pages: list[str], warnings: list[dict], minimum: int) -> list[dict]:
    ocr_warnings = [item for item in warnings if item.get("strategy") == "ocr"]
    if not ocr_warnings:
        return warnings
    image_counts = [0] * len(pages)
    for item in ocr_warnings:
        image_counts[int(item["page"]) - 1] = 1
    allowed = _ocr_candidate_pages(pages, image_counts, minimum)
    return [
        item for item in warnings if item.get("strategy") != "ocr" or int(item["page"]) in allowed
    ]


@lru_cache(maxsize=1)
def _ocr_runtime_available() -> bool:
    try:
        import pytesseract
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    if shutil.which("tesseract") is None:
        return False
    try:
        return "eng" in pytesseract.get_languages(config="")
    except pytesseract.TesseractError:
        return False


def _extract_tables(page) -> str:
    rows = []
    finder = page.find_tables()
    for table in finder.tables:
        for row in table.extract():
            normalized = [" ".join(str(cell or "").split()) for cell in row]
            if any(normalized):
                rows.append(" | ".join(normalized))
    return "\n".join(rows)


def _ocr_page(page, dpi: int) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise OCRUnavailable(
            "OCR fallback required but Python OCR dependencies are unavailable; install .[ocr]."
        ) from exc
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    try:
        return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailable(
            "OCR fallback required but the Tesseract executable is not installed or not on PATH."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise OCRUnavailable(f"Tesseract OCR failed: {exc}") from exc


def find_pages(pages: list[str], *terms: str) -> list[int]:
    lowered = [term.lower() for term in terms]
    return [i for i, text in enumerate(pages, 1) if all(term in text.lower() for term in lowered)]
