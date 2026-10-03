"""Page-preserving PDF extraction."""

from pathlib import Path

import pymupdf


def extract_pages(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [page.get_text("text", sort=True) for page in document]


def find_pages(pages: list[str], *terms: str) -> list[int]:
    lowered = [term.lower() for term in terms]
    return [i for i, text in enumerate(pages, 1) if all(term in text.lower() for term in lowered)]
