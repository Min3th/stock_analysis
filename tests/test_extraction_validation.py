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
