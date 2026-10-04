from pathlib import Path

import pymupdf
import pytest

from cse_screening.parsers.pdf import (
    _extract_tables,
    _needs_ocr,
    _needs_table_extraction,
    _ocr_candidate_pages,
    _ocr_runtime_available,
    extract_document,
)


class _FakeTable:
    def extract(self):
        return [["Revenue", "1,000", "900"], [None, "", None]]


class _FakeFinder:
    def __init__(self):
        self.tables = [_FakeTable()]


class _FakePage:
    def find_tables(self):
        return _FakeFinder()


def test_alternative_table_rows_are_serialized_for_metric_extraction():
    assert _extract_tables(_FakePage()) == "Revenue | 1,000 | 900"


def test_ocr_is_only_requested_for_sparse_pages_with_images():
    assert _needs_ocr("", 1, 80)
    assert not _needs_ocr("", 0, 80)
    assert not _needs_ocr("enough text " * 20, 1, 80)


def test_mixed_pdf_ignores_isolated_decorative_cover_for_ocr():
    pages = ["", "Narrative text " * 20, "Statement of Profit or Loss " * 5]
    assert _ocr_candidate_pages(pages, [1, 0, 0], 80) == set()


def test_fully_scanned_document_routes_image_pages_to_ocr():
    pages = ["", "", "", ""]
    assert _ocr_candidate_pages(pages, [1, 1, 1, 1], 80) == {1, 2, 3, 4}


def test_statement_pages_route_through_table_strategy():
    assert _needs_table_extraction("Statement of Profit or Loss\nRevenue 100 90")


def test_native_pdf_extraction_records_method_and_uses_versioned_cache(tmp_path: Path):
    path = tmp_path / "report.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Statement of Profit or Loss Revenue 100 90")
    document.save(path)
    document.close()

    parsed = extract_document(
        path,
        {
            "ocr": {"enabled": False, "minimum_text_characters_per_page": 80},
            "tables": {"enabled": False},
        },
    )
    assert "Revenue 100 90" in parsed.pages[0]
    assert parsed.methods == ["native_text"]
    assert path.with_suffix(".pdf.pages.v2.json").exists()


@pytest.mark.skipif(not _ocr_runtime_available(), reason="Tesseract OCR runtime is unavailable")
def test_image_only_pdf_is_ocr_extracted_end_to_end(tmp_path: Path):
    source = pymupdf.open()
    source_page = source.new_page(width=800, height=200)
    source_page.insert_text((40, 100), "Revenue 1,000 900", fontsize=36)
    pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    source.close()

    path = tmp_path / "scanned.pdf"
    scanned = pymupdf.open()
    scanned_page = scanned.new_page(width=800, height=200)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    scanned.save(path)
    scanned.close()

    parsed = extract_document(
        path,
        {
            "ocr": {"enabled": True, "minimum_text_characters_per_page": 80, "dpi": 300},
            "tables": {"enabled": False},
        },
    )
    assert "Revenue" in parsed.pages[0]
    assert parsed.methods == ["ocr_tesseract"]
    assert parsed.warnings == []
