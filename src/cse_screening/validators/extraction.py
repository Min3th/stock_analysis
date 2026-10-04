"""Conservative document-level validation for extracted financial facts."""

from __future__ import annotations

from decimal import Decimal


def validate_extracted_facts(
    facts: list[dict],
    *,
    implied_shares: Decimal | None = None,
    multi_class: bool = False,
    check_per_share: bool = True,
) -> list[dict]:
    """Annotate questionable facts and return structured review issues.

    Values are preserved. Validation lowers confidence and makes uncertainty
    visible instead of silently deleting unusual reported results; a fact whose
    confidence falls below the pipeline threshold is kept in the raw data and
    the review file but is not used in the screening table.

    ``implied_shares`` is the share count implied by CSE market data (market
    capitalisation / price) for the listed class. It is only meaningful for the
    latest annual report and for issuers with a single listed share class.
    ``check_per_share`` limits the share-count and book-value reconciliation to
    the document whose values feed the screening table.
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

    issues.extend(_cross_check_per_share(selected, implied_shares, multi_class, check_per_share))
    return issues


SHARE_SCALES = (Decimal(1000), Decimal(1000000))
REVIEW_CONFIDENCE = Decimal("0.60")


def _near(value: Decimal, reference: Decimal, tolerance: Decimal) -> bool:
    return reference != 0 and abs(value - reference) <= abs(reference) * tolerance


def _demote(fact: dict, reason: str, rule: str) -> dict:
    """Mark a fact for review and take it below the screening threshold."""
    fact["validation_status"] = "review"
    notes = fact.get("validation_notes", "")
    fact["validation_notes"] = f"{notes}; {reason}".strip("; ")
    fact["confidence"] = min(fact["confidence"], REVIEW_CONFIDENCE)
    return _issue(fact, reason, rule)


def _cross_check_per_share(
    selected: dict[str, dict],
    implied_shares: Decimal | None,
    multi_class: bool,
    reconcile_counts: bool = True,
) -> list[dict]:
    """Reconcile EPS, share count, book value and dividend per share with each other."""
    issues: list[dict] = []
    eps = selected.get("eps")
    profit = selected.get("net_profit_attributable") or selected.get("net_profit")
    shares = selected.get("ordinary_shares_outstanding")
    market_shares = None if multi_class else implied_shares

    if eps and profit and eps["value"] != 0 and profit["value"] != 0:
        if (eps["value"] > 0) != (profit["value"] > 0):
            reason = (
                f"EPS ({eps['value']}) and profit ({profit['value']}) have opposite signs; "
                "one of them was read from the wrong row or column"
            )
            issues.append(_demote(eps, reason, "eps_profit_sign"))
        elif market_shares:
            expected = profit["value"] / market_shares
            ratio = abs(eps["value"] / expected)
            if not Decimal("0.33") <= ratio <= Decimal(3):
                reason = (
                    f"EPS {eps['value']} is {ratio:.2f}x attributable profit / CSE share count "
                    f"({expected:.2f}); possible wrong row, year label or note reference"
                )
                issues.append(_demote(eps, reason, "eps_identity"))

    references: list[tuple[str, Decimal, Decimal]] = []
    eps_usable = eps is not None and eps.get("validation_status") != "review"
    if eps_usable and profit and eps["value"] != 0 and profit["value"] / eps["value"] > 0:
        references.append(
            ("attributable profit / EPS", profit["value"] / eps["value"], Decimal("0.25"))
        )
    if market_shares:
        references.append(("CSE market capitalisation / price", market_shares, Decimal("0.35")))
    if not reconcile_counts:
        references = []
    if shares is not None and references and shares["value"] not in (None, Decimal(0)):
        matched = next(
            (label for label, ref, tol in references if _near(shares["value"], ref, tol)), None
        )
        if matched:
            _note(shares, f"Share count reconciles with {matched}.")
        else:
            scaled = next(
                (
                    (scale, label)
                    for scale in SHARE_SCALES
                    for label, ref, _ in references
                    if _near(shares["value"] * scale, ref, Decimal("0.05"))
                ),
                None,
            )
            if scaled:
                scale, label = scaled
                shares["value"] = shares["value"] * scale
                shares["multiplier"] = shares.get("multiplier", Decimal(1)) * scale
                shares["original_unit"] = f"shares x {scale:,} (scale inferred)"
                _note(
                    shares,
                    f"Reported in units of {scale:,}: the scaled count matches {label} within 5%.",
                )
            else:
                described = "; ".join(f"{label} = {ref:,.0f}" for label, ref, _ in references)
                reason = (
                    f"Share count {shares['value']:,.0f} does not reconcile with {described} "
                    "(for example a weighted average, a single class, or a pre-split count)"
                )
                issues.append(_demote(shares, reason, "share_count_identity"))

    shares_usable = (
        shares is not None
        and shares.get("validation_status") != "review"
        and shares["confidence"] >= Decimal("0.8")
    )
    share_count = shares["value"] if shares_usable else market_shares
    bvps, equity = selected.get("bvps"), selected.get("ordinary_equity")
    reconcilable = reconcile_counts and bvps and equity and share_count
    if reconcilable and equity["confidence"] >= Decimal("0.8"):
        expected = equity["value"] / share_count
        mismatch = expected > 0 and not _near(bvps["value"], expected, Decimal("0.15"))
        on_statement = str(bvps.get("extraction_method", "")).startswith("primary_")
        if mismatch and on_statement:
            # A figure the issuer prints on the statement itself stands; the
            # difference is recorded for the reviewer.
            reason = (
                f"Book value per share printed on the statement ({bvps['value']}) differs "
                f"from parent equity / shares ({expected:.2f}) by more than 15%; the printed "
                "figure is used"
            )
            _note(bvps, reason)
            issues.append(_issue(bvps, reason, "bvps_identity"))
        elif mismatch:
            reason = (
                f"Reported book value per share {bvps['value']} differs from parent equity / "
                f"shares ({expected:.2f}) by more than 15%; the calculated value is used"
            )
            issues.append(_demote(bvps, reason, "bvps_identity"))

    dps = selected.get("dps")
    if dps is not None and dps["value"] is not None:
        if dps["value"] < 0:
            issues.append(_demote(dps, "Dividend per share cannot be negative", "dps_range"))
        elif eps_usable and dps["value"] > max(abs(eps["value"]) * Decimal(5), Decimal(1)):
            reason = (
                f"Dividend per share {dps['value']} is more than five times EPS "
                f"{eps['value']}; possible note reference or wrong column"
            )
            issues.append(_demote(dps, reason, "dps_range"))
    return issues


def _note(fact: dict, text: str) -> None:
    notes = fact.get("validation_notes", "")
    fact["validation_notes"] = f"{notes}; {text}".strip("; ")


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
