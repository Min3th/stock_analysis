"""Conservative document-level validation for extracted financial facts."""

from __future__ import annotations

from decimal import Decimal


def validate_extracted_facts(facts: list[dict]) -> list[dict]:
    """Annotate questionable facts and return structured review issues.

    Values are preserved. Validation lowers confidence and makes uncertainty
    visible instead of silently deleting unusual reported results.
    """
    issues: list[dict] = []
    selected: dict[str, dict] = {}
    for fact in facts:
        prior = selected.get(fact["metric"])
        if prior is None or fact["confidence"] > prior["confidence"]:
            selected[fact["metric"]] = fact
        fact.setdefault("validation_status", "passed")
        fact.setdefault("validation_notes", "")

    for fact in facts:
        if fact["confidence"] < Decimal("0.8"):
            reason = (
                "Reported unit or statement-column context could not be established "
                f"with high confidence; extraction confidence={fact['confidence']}"
            )
            _warn([fact], reason, Decimal(0))
            issues.append(_issue(fact, reason, "low_confidence"))

    assets = selected.get("total_assets")
    liabilities = selected.get("total_liabilities")
    equity = selected.get("total_equity")
    if assets and liabilities and equity and assets.get("value") not in {None, Decimal(0)}:
        difference = abs(assets["value"] - liabilities["value"] - equity["value"])
        tolerance = max(abs(assets["value"]) * Decimal("0.05"), Decimal(1))
        if difference > tolerance:
            reason = (
                "Accounting equation failed: total assets differ from total liabilities plus "
                f"total equity by {difference} LKR (>5% tolerance)"
            )
            affected = [assets, liabilities, equity]
            _warn(affected, reason, Decimal("0.15"))
            issues.extend(_issue(fact, reason, "accounting_equation") for fact in affected)

    revenue = selected.get("revenue")
    profit = selected.get("net_profit")
    if (
        revenue
        and profit
        and revenue.get("value") not in {None, Decimal(0)}
        and abs(profit["value"]) > abs(revenue["value"]) * Decimal(2)
    ):
        reason = (
            "Net profit magnitude exceeds twice revenue; possible unit, scope, holding-company, "
            "or row-selection mismatch"
        )
        _warn([revenue, profit], reason, Decimal("0.12"))
        issues.extend(_issue(fact, reason, "profit_revenue_scale") for fact in (revenue, profit))

    return issues


def cross_period_issues(
    annual_facts: dict[str, dict], interim_facts: list[dict], months: int
) -> list[dict]:
    """Identify strong annual/YTD scale conflicts without discarding either fact."""
    if not 1 <= months <= 11:
        return []
    issues = []
    for interim in interim_facts:
        annual = annual_facts.get(interim["metric"])
        if annual is None or interim["metric"] not in {
            "revenue",
            "operating_profit",
            "net_profit",
            "net_profit_attributable",
        }:
            continue
        annual_value, interim_value = annual.get("value"), interim.get("value")
        if annual_value in {None, Decimal(0)} or interim_value is None:
            continue
        # A partial period over 20x the latest full year is strong evidence of a
        # scale/scope mismatch while still allowing substantial genuine growth.
        if abs(interim_value) > abs(annual_value) * Decimal(20):
            reason = (
                f"{months}-month value is over 20x the latest annual value; possible unit or "
                "statement-scope mismatch"
            )
            _warn([annual, interim], reason, Decimal("0.15"))
            issues.extend(_issue(fact, reason, "cross_period_scale") for fact in (annual, interim))
    return issues


def _warn(facts: list[dict], reason: str, downgrade: Decimal) -> None:
    for fact in facts:
        fact["validation_status"] = "review"
        notes = fact.get("validation_notes", "")
        fact["validation_notes"] = f"{notes}; {reason}".strip("; ")
        fact["confidence"] = max(Decimal(0), fact["confidence"] - downgrade)


def _issue(fact: dict, reason: str, rule: str) -> dict:
    candidates = fact.get("comparatives") or [fact.get("original_value")]
    return {
        "metric": fact["metric"],
        "candidate_values": "; ".join(str(value) for value in candidates if value is not None),
        "source_page": fact["page"],
        "source_text": fact["source_text"],
        "reason": reason,
        "rule": rule,
        "strategy": fact.get("extraction_method", "unknown"),
    }
