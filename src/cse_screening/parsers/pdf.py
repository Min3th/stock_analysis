"""Page-preserving PDF extraction."""

import json
from pathlib import Path

import pymupdf


def extract_pages(path: Path) -> list[str]:
    cache = path.with_suffix(f"{path.suffix}.pages.json")
    if cache.exists() and cache.stat().st_size:
        return json.loads(cache.read_text(encoding="utf-8"))
    with pymupdf.open(path) as document:
        pages = [page.get_text("text", sort=True) for page in document]
    cache.write_text(json.dumps(pages), encoding="utf-8")
    return pages


def find_pages(pages: list[str], *terms: str) -> list[int]:
    lowered = [term.lower() for term in terms]
    return [i for i, text in enumerate(pages, 1) if all(term in text.lower() for term in lowered)]
