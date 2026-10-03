from decimal import Decimal
from pathlib import Path

import pytest

from cse_screening.corrections import correction_candidates, load_corrections


def test_correction_is_normalized_and_matches_exact_document(tmp_path: Path):
    path = tmp_path / "corrections.yml"
    path.write_text(
        """corrections:
  - id: acl-revenue-fy26-v1
    ticker: ACL.N0000
    metric: revenue
    financial_period: 2026-03-31
    source_document: Annual Report 2025/26
    value: '123.4'
    unit: LKR million
    source_page: 122
    statement_scope: group
    reason: Verified consolidated column manually
    author: analyst
    corrected_at: 2026-10-03
""",
        encoding="utf-8",
    )
    items = load_corrections(path)
    candidates = correction_candidates(
        items,
        "ACL.N0000",
        {"title": "Annual Report 2025/26", "period_end": "2026-03-31"},
    )
    assert candidates[0]["value"] == Decimal("123400000.0")
    assert candidates[0]["confidence"] == Decimal(1)
    assert candidates[0]["correction_id"] == "acl-revenue-fy26-v1"


def test_superseded_correction_is_retained_but_not_applied(tmp_path: Path):
    path = tmp_path / "corrections.yml"
    path.write_text(
        """corrections:
  - id: old
    status: superseded
    ticker: ACL.N0000
    metric: revenue
    financial_period: 2026-03-31
    source_document: Annual Report 2025/26
    value: 100
    unit: LKR
    source_page: 1
    statement_scope: group
    reason: Replaced after second review
    author: analyst
    corrected_at: 2026-10-02
""",
        encoding="utf-8",
    )
    assert (
        correction_candidates(
            load_corrections(path),
            "ACL.N0000",
            {"title": "Annual Report 2025/26", "period_end": "2026-03-31"},
        )
        == []
    )


def test_duplicate_active_target_is_rejected(tmp_path: Path):
    path = tmp_path / "corrections.yml"
    common = """    ticker: ACL.N0000
    metric: revenue
    financial_period: 2026-03-31
    source_document: Annual Report 2025/26
    value: 100
    unit: LKR
    source_page: 1
    statement_scope: group
    reason: Verified manually
    author: analyst
    corrected_at: 2026-10-03
"""
    path.write_text(f"corrections:\n  - id: one\n{common}  - id: two\n{common}", encoding="utf-8")
    with pytest.raises(ValueError, match="multiple active corrections"):
        load_corrections(path)
