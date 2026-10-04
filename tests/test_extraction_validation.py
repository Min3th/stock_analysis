from decimal import Decimal as D

from cse_screening.validators.extraction import validate_extracted_facts


def fact(metric, value, confidence="0.9"):
    return {
        "metric": metric,
        "value": D(value),
        "original_value": D(value),
        "comparatives": [D(value), D(value)],
        "page": 1,
        "source_text": f"{metric} {value}",
        "confidence": D(confidence),
        "extraction_method": "statement_label_line",
    }


def test_accounting_equation_failure_downgrades_and_retains_values():
    facts = [
        fact("total_assets", "100"),
        fact("total_liabilities", "20"),
        fact("total_equity", "30"),
    ]
    issues = validate_extracted_facts(facts)
    assert {item["rule"] for item in issues} == {"accounting_equation"}
    assert facts[0]["value"] == D(100)
    assert facts[0]["confidence"] == D("0.75")
    assert facts[0]["validation_status"] == "review"


def test_balanced_statement_passes_validation():
    facts = [
        fact("total_assets", "100"),
        fact("total_liabilities", "60"),
        fact("total_equity", "40"),
    ]
    assert validate_extracted_facts(facts) == []
    assert all(item["validation_status"] == "passed" for item in facts)


def test_low_confidence_candidate_is_exportable_for_review():
    facts = [fact("revenue", "100", "0.62")]
    issues = validate_extracted_facts(facts)
    assert issues[0]["candidate_values"] == "100; 100"
    assert issues[0]["source_page"] == 1
    assert issues[0]["strategy"] == "statement_label_line"
    assert issues[0]["rule"] == "low_confidence"


def per_share_facts(**overrides):
    values = {
        "net_profit_attributable": fact("net_profit_attributable", "1180000000"),
        "eps": fact("eps", "4.45"),
        "ordinary_equity": fact("ordinary_equity", "16107000000"),
        "ordinary_shares_outstanding": fact("ordinary_shares_outstanding", "265252050"),
    }
    values.update(overrides)
    return [item for item in values.values() if item is not None]


def by_metric(facts):
    return {item["metric"]: item for item in facts}


def test_share_count_reported_in_thousands_is_rescaled_with_a_note():
    facts = per_share_facts(
        ordinary_shares_outstanding=fact("ordinary_shares_outstanding", "265252")
    )
    assert validate_extracted_facts(facts) == []
    shares = by_metric(facts)["ordinary_shares_outstanding"]
    assert shares["value"] == D(265252000)
    assert "units of 1,000" in shares["validation_notes"]
    assert shares["confidence"] == D("0.9")


def test_share_count_that_matches_nothing_is_withheld():
    facts = per_share_facts(
        ordinary_shares_outstanding=fact("ordinary_shares_outstanding", "60471501")
    )
    issues = validate_extracted_facts(facts, implied_shares=D(265000000))
    assert [item["rule"] for item in issues] == ["share_count_identity"]
    shares = by_metric(facts)["ordinary_shares_outstanding"]
    assert shares["value"] == D(60471501)
    assert shares["confidence"] == D("0.60")


def test_eps_with_the_wrong_sign_or_magnitude_is_withheld():
    facts = per_share_facts(eps=fact("eps", "-4.45"))
    assert "eps_profit_sign" in {item["rule"] for item in validate_extracted_facts(facts)}
    assert by_metric(facts)["eps"]["confidence"] == D("0.60")
    facts = per_share_facts(eps=fact("eps", "2025"), ordinary_shares_outstanding=None)
    issues = validate_extracted_facts(facts, implied_shares=D(265252050))
    assert [item["rule"] for item in issues] == ["eps_identity"]


def test_reported_book_value_is_checked_against_equity_and_shares():
    highlight = dict(fact("bvps", "16.00"), extraction_method="statement_label_line")
    facts = per_share_facts(bvps=highlight)
    assert [item["rule"] for item in validate_extracted_facts(facts)] == ["bvps_identity"]
    assert by_metric(facts)["bvps"]["confidence"] == D("0.60")
    printed = dict(fact("bvps", "75.00"), extraction_method="primary_position_row+native_text")
    facts = per_share_facts(bvps=printed)
    assert [item["rule"] for item in validate_extracted_facts(facts)] == ["bvps_identity"]
    assert by_metric(facts)["bvps"]["confidence"] == D("0.9")
    agreeing = per_share_facts(bvps=fact("bvps", "60.72"))
    assert validate_extracted_facts(agreeing) == []


def test_dividend_far_above_earnings_is_withheld():
    facts = per_share_facts(dps=fact("dps", "36.30"))
    assert [item["rule"] for item in validate_extracted_facts(facts)] == ["dps_range"]


def test_older_reports_skip_the_share_reconciliation():
    facts = per_share_facts(
        ordinary_shares_outstanding=fact("ordinary_shares_outstanding", "60471501")
    )
    assert validate_extracted_facts(facts, check_per_share=False) == []
