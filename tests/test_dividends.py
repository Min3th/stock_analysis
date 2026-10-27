from datetime import date
from decimal import Decimal

from cse_screening.calculations.dividends import dps_conflict, financial_year_dividends


def _announcement(identifier, kind, fy, voting=0, non_voting=0, remarks="", dtype="CashDividend"):
    flags = {
        "interim": "typeFirstInt",
        "second interim": "typeSecondInt",
        "final": "finalDividend",
        "first and final": "firstAndFinal",
        "other": "typeOther",
    }
    return {
        "reqBaseAnnouncement": {
            "id": identifier,
            "dType": dtype,
            "financialYear": fy,
            "votingDivPerShare": voting,
            "nonVotingDivPerShare": non_voting,
            "remarks": remarks,
            flags.get(kind, "typeFirstInt"): True,
        }
    }


def test_interim_and_final_are_summed_for_one_financial_year():
    years = financial_year_dividends(
        [
            _announcement(1, "interim", "31st March 2026", voting=0.60),
            _announcement(2, "final", "31st March 2026", voting=1.10),
        ],
        "ACL.N0000",
    )
    year = years[date(2026, 3, 31)]
    assert year.dps == Decimal("1.7")
    assert year.complete and year.announcement_ids == [1, 2]


def test_final_declared_after_year_end_belongs_to_the_year_it_is_for():
    years = financial_year_dividends(
        [
            _announcement(1, "interim", "31st March 2025", voting=0.50),
            _announcement(2, "final", "31st March 2025", voting=0.75),
            _announcement(9, "interim", "31st March 2026", voting=0.60),
        ],
        "ACL.N0000",
    )
    assert years[date(2025, 3, 31)].dps == Decimal("1.25")
    assert years[date(2025, 3, 31)].complete
    # Only an interim so far for FY2026: a partial sum, not the year's dividend.
    assert years[date(2026, 3, 31)].dps == Decimal("0.6")
    assert not years[date(2026, 3, 31)].complete


def test_scrip_and_stock_dividends_are_not_cash():
    years = financial_year_dividends(
        [
            _announcement(1, "final", "31st March 2026", voting=1.0, remarks="Scrip dividend"),
            _announcement(2, "final", "31st March 2026", voting=2.0, dtype="ScripDividend"),
        ],
        "ACL.N0000",
    )
    assert years == {}


def test_missing_year_and_unusable_announcements_give_nothing():
    years = financial_year_dividends(
        [
            _announcement(1, "final", "", voting=1.0),
            _announcement(2, "other", "31st March 2026", voting=1.0),
            _announcement(3, "final", "31st March 2026", voting=0),
        ],
        "ACL.N0000",
    )
    assert years == {}


def test_amended_announcement_replaces_the_earlier_one():
    years = financial_year_dividends(
        [
            _announcement(5, "final", "31st March 2026", voting=1.0),
            _announcement(8, "final", "31st March 2026", voting=1.2),
        ],
        "ACL.N0000",
    )
    assert years[date(2026, 3, 31)].dps == Decimal("1.2")
    assert years[date(2026, 3, 31)].announcement_ids == [8]


def test_non_voting_ticker_uses_the_non_voting_amount():
    announcements = [_announcement(1, "final", "31st March 2026", voting=2.0, non_voting=1.5)]
    assert financial_year_dividends(announcements, "ABC.X0000")[date(2026, 3, 31)].dps == Decimal(
        "1.5"
    )
    assert financial_year_dividends(announcements, "ABC.N0000")[date(2026, 3, 31)].dps == Decimal(
        "2.0"
    )


def test_conflict_tolerance():
    assert not dps_conflict(Decimal("1.00"), Decimal("1.03"))
    assert dps_conflict(Decimal("1.00"), Decimal("1.50"))


def _snapshot(without_dps: bool):
    import json
    from pathlib import Path

    from cse_screening.calculations.screening import build_snapshot
    from cse_screening.extractors.statements import extract_document_metrics

    path = Path(__file__).parent / "fixtures" / "banks" / "ntb_annual.json"
    pages = json.loads(path.read_text(encoding="utf-8"))["pages"]
    facts = extract_document_metrics(pages, "annual_report", "bank")
    for fact in facts:
        fact["fact_id"] = f"NTB:{fact['metric']}"
    if without_dps:
        facts = [fact for fact in facts if fact["metric"] != "dps"]
    document = {"kind": "annual_report", "period_end": "2025-12-31", "title": "AR"}
    return build_snapshot("NTB.N0000", [(document, facts)], lambda fact: True)


def _year(complete: bool):
    from cse_screening.calculations.dividends import FinancialYearDividend

    return FinancialYearDividend(
        date(2025, 12, 31), Decimal("7.5"), complete, [11, 12], ["interim", "final"]
    )


def test_announced_total_fills_a_missing_statement_dps():
    from cse_screening.calculations.screening import screening_metrics

    values, rows = screening_metrics(_snapshot(True), Decimal(100), [], None, _year(True))
    assert values["DPS"] == Decimal("7.5") and values["DPS Basis"] == "announced_fy"
    assert values["Dividend Yield"] == Decimal("0.075")
    row = next(item for item in rows if item["Metric"] == "DPS")
    assert "11, 12" in row["Notes"] and row["Status"] == "calculated"


def test_partial_year_announcements_do_not_become_the_years_dps():
    from cse_screening.calculations.screening import screening_metrics

    values, _ = screening_metrics(_snapshot(True), Decimal(100), [], None, _year(False))
    assert values["DPS"] is None and values["DPS Basis"] is None


def test_statement_dps_wins_over_announcements():
    from cse_screening.calculations.screening import screening_metrics

    snapshot = _snapshot(False)
    statement = snapshot.annual_value("dps")
    assert statement is not None
    values, _ = screening_metrics(snapshot, Decimal(100), [], None, _year(True))
    assert values["DPS"] == statement and values["DPS Basis"] == "statement"
