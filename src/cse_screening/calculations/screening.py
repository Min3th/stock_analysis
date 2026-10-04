"""Period-safe selection of facts and calculation of screening metrics.

A screening row never mixes periods silently. Balance-sheet figures come from
the latest annual report. Income and cash-flow figures are trailing twelve
months when the latest interim statement provides a proven year-to-date pair,
and otherwise the latest financial year; a bare interim figure is never used
on its own. Every calculated value carries the basis it was calculated on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..periods import ttm_from_annual_and_ytd
from .ratios import (
    cagr,
    debt_to_equity,
    divide,
    dividend_yield,
    free_cash_flow,
    growth,
    net_debt,
    payout_ratio,
    price_earnings,
    price_to_book,
    roa,
    roe,
)

INCOME_FLOWS = (
    "revenue",
    "operating_profit",
    "ebit",
    "net_profit",
    "net_profit_attributable",
    "eps",
)
CASH_FLOWS = ("operating_cash_flow", "capital_expenditure")
INCOME_ANCHORS = ("revenue", "net_profit", "eps")
YEAR_TO_DATE = 0
RESTATEMENT_TOLERANCE = {"eps": Decimal("0.02"), "revenue": Decimal("0.10")}

SCREEN_COLUMNS = [
    # Columns required by the screening specification, in its order.
    "Ticker",
    "Company",
    "Current Price",
    "Market Cap",
    "Revenue",
    "Revenue Growth YoY",
    "Net Profit",
    "EPS",
    "EPS Growth YoY",
    "3Y Revenue CAGR",
    "3Y EPS CAGR",
    "ROE",
    "ROA",
    "Debt-to-Equity",
    "Net Debt",
    "Operating Cash Flow",
    "Free Cash Flow",
    "OCF / Net Profit",
    "P/E",
    "P/B",
    "DPS",
    "Dividend Yield",
    "Payout Ratio",
    "Earnings Yield",
    "Latest Financial Period",
    "Data Confidence",
    "Flags",
    # Supporting columns.
    "Net Profit Growth YoY",
    "Operating Profit",
    "EBIT",
    "Book Value Per Share",
    "Ordinary Shares Outstanding",
    "Retained Earnings",
    "Income Period Basis",
    "Cash Flow Period Basis",
    "Balance Sheet Date",
    "Recent Volume",
    "Average Daily Volume",
    "Median Daily Volume",
    "Liquidity Trading Days",
    "Liquidity Period",
]


def _always(_fact: dict) -> bool:
    return True


@dataclass
class Snapshot:
    """Facts selected for one company, with the period each group covers."""

    ticker: str
    annual: dict[str, dict] = field(default_factory=dict)
    annual_end: date | None = None
    annual_months: int = 12
    ttm: dict[str, dict] = field(default_factory=dict)
    ttm_end: date | None = None
    income_basis: str = "fy"
    cash_basis: str = "fy"
    notes: list[str] = field(default_factory=list)
    lineage: list[dict] = field(default_factory=list)

    def fy_label(self) -> str | None:
        if self.annual_end is None:
            return None
        span = "FY" if self.annual_months == 12 else f"{self.annual_months} months"
        return f"{span} to {self.annual_end.isoformat()}"

    def ttm_label(self) -> str | None:
        return f"TTM to {self.ttm_end.isoformat()}" if self.ttm_end else None

    def basis_label(self, group: str) -> str | None:
        basis = self.income_basis if group == "income" else self.cash_basis
        return self.ttm_label() if basis == "ttm" else self.fy_label()

    def flow(self, metric: str) -> dict | None:
        """The fact used for a flow metric on the company's period basis."""
        group = "income" if metric in INCOME_FLOWS else "cash"
        basis = self.income_basis if group == "income" else self.cash_basis
        return self.ttm.get(metric) if basis == "ttm" else self.annual.get(metric)

    def flow_value(self, metric: str) -> Decimal | None:
        fact = self.flow(metric)
        return None if fact is None else fact["value"]

    def annual_value(self, metric: str) -> Decimal | None:
        fact = self.annual.get(metric)
        return None if fact is None else fact["value"]

    def annual_previous(self, metric: str) -> Decimal | None:
        fact = self.annual.get(metric)
        return None if fact is None else previous_value(fact)


def previous_value(fact: dict) -> Decimal | None:
    """Comparative-column value in base units."""
    if fact.get("previous_value") is not None:
        return fact["previous_value"]
    comparatives = fact.get("comparatives") or []
    if len(comparatives) >= 2 and comparatives[1] is not None:
        return comparatives[1] * fact.get("multiplier", Decimal(1))
    return None


def _best(facts: list[dict], usable: Callable[[dict], bool]) -> dict[str, dict]:
    """One usable fact per metric; a manual correction outranks an extraction."""
    selected: dict[str, dict] = {}
    for fact in facts:
        if fact.get("value") is None or not usable(fact):
            continue
        prior = selected.get(fact["metric"])
        rank = (bool(fact.get("correction_id")), fact["confidence"])
        if prior is None or rank > (bool(prior.get("correction_id")), prior["confidence"]):
            selected[fact["metric"]] = fact
    return selected


def build_snapshot(
    ticker: str,
    document_facts: list[tuple[dict, list[dict]]],
    usable: Callable[[dict], bool] = _always,
) -> Snapshot:
    """Select the latest annual facts and construct TTM flows where proven."""
    snapshot = Snapshot(ticker=ticker)
    annuals = [item for item in document_facts if item[0]["kind"] == "annual_report"]
    if not annuals:
        snapshot.notes.append("No annual report was processed; annual metrics are unavailable.")
        return snapshot
    document, facts = max(annuals, key=lambda item: str(item[0]["period_end"]))
    snapshot.annual_end = date.fromisoformat(str(document["period_end"]))
    snapshot.annual = _best(facts, usable)
    lengths = {
        fact.get("period_months")
        for metric, fact in snapshot.annual.items()
        if metric in (*INCOME_FLOWS, *CASH_FLOWS) and fact.get("period_months")
    }
    if lengths and lengths != {12}:
        snapshot.annual_months = max(lengths)
        snapshot.notes.append(
            f"The latest financial statements cover {snapshot.annual_months} months; growth, "
            "TTM and per-year comparisons against a twelve-month year are not calculated."
        )
        return snapshot

    interims = [
        item
        for item in document_facts
        if item[0]["kind"] == "interim_statement"
        and str(item[0]["period_end"]) > str(document["period_end"])
    ]
    if not interims:
        return snapshot
    interim_document, interim_facts = max(interims, key=lambda item: str(item[0]["period_end"]))
    months = interim_document.get("period_months")
    prior_end = interim_document.get("comparative_period_end")
    if not months or not prior_end:
        snapshot.notes.append(
            "The latest interim statement has no confirmed year-to-date length; "
            "latest financial-year figures are used."
        )
        return snapshot
    current_end = date.fromisoformat(str(interim_document["period_end"]))
    interim = _best(interim_facts, usable)
    for metric in (*INCOME_FLOWS, *CASH_FLOWS):
        annual, current = snapshot.annual.get(metric), interim.get(metric)
        if annual is None or current is None:
            continue
        stated = current.get("period_months")
        if stated not in (int(months), YEAR_TO_DATE):
            snapshot.notes.append(
                f"{metric}: interim columns are not confirmed as the {months}-month year to "
                "date, so no TTM value is built."
            )
            continue
        prior = previous_value(current)
        result = ttm_from_annual_and_ytd(
            annual["value"],
            current["value"],
            prior,
            annual_end=snapshot.annual_end,
            current_end=current_end,
            prior_end=date.fromisoformat(str(prior_end)),
            months=int(months),
        )
        if result is None:
            continue
        if metric == "revenue" and not _plausible_ytd(annual["value"], current["value"], months):
            snapshot.notes.append(
                "revenue: the interim year-to-date value is out of proportion to the latest "
                "annual value (possible unit or scope mismatch); no TTM value is built."
            )
            continue
        fact_id = f"{ticker}:TTM:{metric}:{current_end.isoformat()}"
        snapshot.ttm[metric] = {
            "metric": metric,
            "value": result,
            "confidence": min(annual["confidence"], current["confidence"]),
            "fact_id": fact_id,
            "page": current["page"],
            "inputs": [annual, current],
        }
        snapshot.lineage.append(
            {
                "Ticker": ticker,
                "Metric": f"{metric} (TTM)",
                "Value": result,
                "Formula": "Latest FY + current YTD - prior comparable YTD",
                "Numerator": annual["value"],
                "Denominator": None,
                "Current YTD": current["value"],
                "Prior YTD": prior,
                "Input Fact IDs": "; ".join(
                    str(item.get("fact_id", "")) for item in (annual, current)
                ),
                "Source Pages": f"{annual['page']}; {current['page']}",
                "Period Basis": f"TTM to {current_end.isoformat()}",
                "Notes": "Per-share TTM is additive and assumes an unchanged share count."
                if metric == "eps"
                else None,
            }
        )
    snapshot.ttm_end = current_end if snapshot.ttm else None
    if _complete(snapshot, INCOME_ANCHORS):
        snapshot.income_basis = "ttm"
    if _complete(snapshot, CASH_FLOWS[:1]) and (
        "capital_expenditure" not in snapshot.annual or "capital_expenditure" in snapshot.ttm
    ):
        snapshot.cash_basis = "ttm"
    return snapshot


def _plausible_ytd(annual: Decimal, current: Decimal, months: int) -> bool:
    if annual == 0:
        return False
    share = abs(current) / abs(annual)
    expected = Decimal(int(months)) / Decimal(12)
    return expected / Decimal(4) <= share <= expected * Decimal(4)


def _complete(snapshot: Snapshot, anchors: tuple[str, ...]) -> bool:
    present = [metric for metric in anchors if metric in snapshot.annual]
    return bool(present) and all(metric in snapshot.ttm for metric in present)


def _ids(*facts: dict | None) -> str:
    return "; ".join(str(fact["fact_id"]) for fact in facts if fact and fact.get("fact_id"))


def _pages(*facts: dict | None) -> str:
    return "; ".join(str(fact["page"]) for fact in facts if fact and fact.get("page"))


def _ratio(
    ticker: str,
    metric: str,
    value,
    formula: str,
    numerator,
    denominator,
    basis: str | None,
    *facts: dict | None,
    notes: str | None = None,
) -> dict:
    return {
        "Ticker": ticker,
        "Metric": metric,
        "Value": value,
        "Formula": formula,
        "Numerator": numerator,
        "Denominator": denominator,
        "Input Fact IDs": _ids(*facts),
        "Source Pages": _pages(*facts),
        "Period Basis": basis,
        "Notes": notes,
    }


def growth_metrics(snapshot: Snapshot, history: list[dict]) -> tuple[dict, list[dict]]:
    """Year-on-year growth and three-year CAGR with their inputs.

    Growth compares the current and comparative columns of the latest annual
    statement, so both years are on the basis the issuer last reported (after
    any restatement or share split). CAGR needs a third year from an earlier
    report and is withheld when that report disagrees with the later
    comparative, because the series is then not on a common basis.
    """
    values: dict[str, Decimal | None] = {}
    rows: list[dict] = []
    ticker = snapshot.ticker
    fy = snapshot.fy_label()
    for label, metric in (
        ("Revenue Growth YoY", "revenue"),
        ("Net Profit Growth YoY", "net_profit"),
        ("EPS Growth YoY", "eps"),
    ):
        fact = snapshot.annual.get(metric)
        current = fact["value"] if fact else None
        previous = previous_value(fact) if fact else None
        note = None
        if snapshot.annual_months != 12:
            result = None
            note = f"Not calculated: the latest period covers {snapshot.annual_months} months."
        else:
            result = growth(current, previous)
            if fact is not None and previous is None:
                note = "Comparative-year value not available on the latest annual statement."
        values[label] = result
        rows.append(
            _ratio(
                ticker,
                label,
                result,
                "(Latest FY - prior FY) / |prior FY|, both from the latest annual statement",
                current,
                previous,
                f"{fy} vs prior year" if fy else None,
                fact,
                notes=note,
            )
        )
    for label, metric in (("3Y Revenue CAGR", "revenue"), ("3Y EPS CAGR", "eps")):
        result, start, end, note = _three_year_cagr(snapshot, history, metric)
        values[label] = result
        rows.append(
            {
                "Ticker": ticker,
                "Metric": label,
                "Value": result,
                "Formula": "(Latest FY / FY two years earlier) ^ (1/2) - 1",
                "Numerator": end["Value"] if end else None,
                "Denominator": start["Value"] if start else None,
                "Input Fact IDs": "; ".join(
                    f"{item['Source Document']} ({item['Value Basis']})"
                    for item in (end, start)
                    if item
                ),
                "Source Pages": "; ".join(
                    str(item["Source Page"]) for item in (end, start) if item
                ),
                "Period Basis": (
                    f"FY {start['Financial Year End']} to FY {end['Financial Year End']}"
                    if start and end
                    else None
                ),
                "Notes": note,
            }
        )
    return values, rows


def _observation(history: list[dict], year_end: str, source_end: str) -> dict | None:
    return next(
        (
            item
            for item in history
            if item["Financial Year End"] == year_end and item["Source Period End"] == source_end
        ),
        None,
    )


def _three_year_cagr(snapshot: Snapshot, history: list[dict], metric: str):
    """CAGR over two years from a chain of adjacent reports on one basis.

    The start value is the comparative printed in the middle year's report, and
    that report's own figure must agree with the comparative in the latest
    report. A break in the chain (a share split, a restatement, a missing
    report) withholds the result instead of comparing unlike figures.
    """
    fact = snapshot.annual.get(metric)
    if snapshot.annual_months != 12:
        return None, None, None, "Not calculated: the latest period is not twelve months."
    if fact is None or snapshot.annual_end is None:
        return None, None, None, "The latest annual value is not available."
    series = [
        item for item in history if item["Ticker"] == snapshot.ticker and item["Metric"] == metric
    ]
    latest_end = snapshot.annual_end
    try:
        middle_end = latest_end.replace(year=latest_end.year - 1)
        start_end = latest_end.replace(year=latest_end.year - 2)
    except ValueError:
        middle_end = latest_end.replace(year=latest_end.year - 1, day=28)
        start_end = latest_end.replace(year=latest_end.year - 2, day=28)
    end = _observation(series, str(latest_end), str(latest_end))
    middle = _observation(series, str(middle_end), str(middle_end))
    start = _observation(series, str(start_end), str(middle_end))
    if end is None or middle is None or start is None:
        return (
            None,
            start,
            end,
            "Needs the latest two consecutive annual reports, each with a comparative year.",
        )
    restated = previous_value(fact)
    reported = middle["Value"]
    tolerance = RESTATEMENT_TOLERANCE.get(metric, Decimal("0.10"))
    if restated is None or reported == 0:
        return None, start, end, "The prior-year comparative is unavailable for a basis check."
    if abs(restated - reported) > abs(reported) * tolerance:
        return (
            None,
            start,
            end,
            (
                f"Withheld: the prior-year value was restated from {reported} to {restated} "
                "in the latest report (for example a share split or reclassification), so "
                "the three-year series is not on a common basis."
            ),
        )
    result = cagr(end["Value"], start["Value"], 2)
    note = None if result is not None else "Undefined for a non-positive start or negative end."
    return result, start, end, note


def _positive(value: Decimal | None) -> Decimal | None:
    """A denominator only when it is positive; ratios on a negative base mislead."""
    return value if value is not None and value > 0 else None


NOT_MEANINGFUL = "Not meaningful: the denominator is zero or negative; the raw value is kept."


def _not_meaningful(denominator: Decimal | None) -> str | None:
    return NOT_MEANINGFUL if denominator is not None and denominator <= 0 else None


def screening_metrics(
    snapshot: Snapshot, price: Decimal | None, history: list[dict]
) -> tuple[dict, list[dict]]:
    """Calculate every screening metric and its lineage rows."""
    ticker = snapshot.ticker
    annual = snapshot.annual
    fy = snapshot.fy_label()
    income_label = snapshot.basis_label("income")
    cash_label = snapshot.basis_label("cash")
    rows: list[dict] = list(snapshot.lineage)
    values: dict[str, object] = {}

    for column, metric in (
        ("Revenue", "revenue"),
        ("Net Profit", "net_profit"),
        ("EPS", "eps"),
        ("Operating Profit", "operating_profit"),
    ):
        values[column] = snapshot.flow_value(metric)
    explicit_ebit, operating = snapshot.flow("ebit"), snapshot.flow("operating_profit")
    ebit_fact = explicit_ebit or operating
    values["EBIT"] = ebit_fact["value"] if ebit_fact else None
    rows.append(
        _ratio(
            ticker,
            "EBIT",
            values["EBIT"],
            "Reported EBIT" if explicit_ebit else "Operating profit used as EBIT proxy",
            values["EBIT"],
            None,
            income_label,
            ebit_fact,
            notes=None
            if explicit_ebit or ebit_fact is None
            else "Proxy is explicitly labelled; no reported EBIT line was accepted.",
        )
    )

    growth_values, growth_rows = growth_metrics(snapshot, history)
    values.update(growth_values)
    rows.extend(growth_rows)

    equity_metric = "ordinary_equity" if "ordinary_equity" in annual else "total_equity"
    profit_metric = (
        "net_profit_attributable" if "net_profit_attributable" in annual else "net_profit"
    )
    equity, equity_prior = (
        snapshot.annual_value(equity_metric),
        snapshot.annual_previous(equity_metric),
    )
    profit = snapshot.annual_value(profit_metric)
    average_equity = (
        (equity + equity_prior) / Decimal(2)
        if equity is not None and equity_prior is not None
        else None
    )
    equity_base_ok = _positive(average_equity) is not None
    values["ROE"] = (
        roe(profit, equity, equity_prior)
        if snapshot.annual_months == 12 and equity_base_ok
        else None
    )
    rows.append(
        _ratio(
            ticker,
            "ROE",
            values["ROE"],
            "Net profit attributable to ordinary shareholders / average ordinary equity",
            profit,
            average_equity,
            fy,
            annual.get(profit_metric),
            annual.get(equity_metric),
            notes=_join_notes(
                None
                if profit_metric == "net_profit_attributable"
                else "Net profit for the year used: no attributable-profit row was accepted.",
                None
                if equity_metric == "ordinary_equity"
                else "Total equity used: no parent-equity value was accepted.",
                None
                if average_equity is not None or equity is None
                else "Opening equity unavailable; ROE on closing equity alone is not calculated.",
                _not_meaningful(average_equity),
            ),
        )
    )
    assets, assets_prior = (
        snapshot.annual_value("total_assets"),
        snapshot.annual_previous("total_assets"),
    )
    net_profit = snapshot.annual_value("net_profit")
    values["ROA"] = roa(net_profit, assets, assets_prior) if snapshot.annual_months == 12 else None
    rows.append(
        _ratio(
            ticker,
            "ROA",
            values["ROA"],
            "Net profit / average total assets",
            net_profit,
            (assets + assets_prior) / Decimal(2)
            if assets is not None and assets_prior is not None
            else None,
            fy,
            annual.get("net_profit"),
            annual.get("total_assets"),
        )
    )

    debt, cash = snapshot.annual_value("total_debt"), snapshot.annual_value("cash")
    balance_date = snapshot.annual_end.isoformat() if snapshot.annual_end else None
    values["Debt-to-Equity"] = debt_to_equity(debt, _positive(equity))
    values["Net Debt"] = net_debt(debt, cash)
    rows.append(
        _ratio(
            ticker,
            "Debt-to-Equity",
            values["Debt-to-Equity"],
            "Total debt / ordinary shareholders' equity",
            debt,
            equity,
            f"As at {balance_date}" if balance_date else None,
            annual.get("total_debt"),
            annual.get(equity_metric),
            notes=_not_meaningful(equity),
        )
    )
    rows.append(
        _ratio(
            ticker,
            "Net Debt",
            values["Net Debt"],
            "Total debt - cash and cash equivalents",
            debt,
            cash,
            f"As at {balance_date}" if balance_date else None,
            annual.get("total_debt"),
            annual.get("cash"),
        )
    )
    values["Retained Earnings"] = snapshot.annual_value("retained_earnings")

    ocf_fact, capex_fact = (
        snapshot.flow("operating_cash_flow"),
        snapshot.flow("capital_expenditure"),
    )
    ocf = ocf_fact["value"] if ocf_fact else None
    capex = capex_fact["value"] if capex_fact else None
    values["Operating Cash Flow"] = ocf
    values["Free Cash Flow"] = free_cash_flow(ocf, capex)
    rows.append(
        _ratio(
            ticker,
            "Free Cash Flow",
            values["Free Cash Flow"],
            "Operating cash flow - |capital expenditure|",
            ocf,
            capex,
            cash_label,
            ocf_fact,
            capex_fact,
        )
    )
    # Both inputs must cover the same period, so the profit follows the cash basis.
    matched_profit = (
        snapshot.ttm.get("net_profit") if snapshot.cash_basis == "ttm" else annual.get("net_profit")
    )
    matched_value = matched_profit["value"] if matched_profit else None
    values["OCF / Net Profit"] = divide(ocf, matched_value)
    rows.append(
        _ratio(
            ticker,
            "OCF / Net Profit",
            values["OCF / Net Profit"],
            "Operating cash flow / net profit",
            ocf,
            matched_value,
            cash_label,
            ocf_fact,
            matched_profit,
            notes=None
            if matched_profit is not None or ocf is None
            else "Net profit is not available for the same period as operating cash flow.",
        )
    )

    eps_fact = snapshot.flow("eps")
    eps = eps_fact["value"] if eps_fact else None
    annual_eps = snapshot.annual_value("eps")
    dps = snapshot.annual_value("dps")
    shares = snapshot.annual_value("ordinary_shares_outstanding")
    reported_bvps = annual.get("bvps")
    if reported_bvps is not None:
        bvps, bvps_formula = reported_bvps["value"], "Reported net assets per share"
        bvps_inputs = (reported_bvps,)
    else:
        bvps = divide(equity, shares) if equity_metric == "ordinary_equity" else None
        bvps_formula = "Ordinary shareholders' equity / ordinary shares outstanding"
        bvps_inputs = (annual.get(equity_metric), annual.get("ordinary_shares_outstanding"))
    values["Book Value Per Share"] = bvps
    values["Ordinary Shares Outstanding"] = shares
    values["DPS"] = dps
    rows.append(
        _ratio(
            ticker,
            "Book Value Per Share",
            bvps,
            bvps_formula,
            bvps if reported_bvps is not None else equity,
            None if reported_bvps is not None else shares,
            f"As at {balance_date}" if balance_date else None,
            *bvps_inputs,
        )
    )
    values["P/E"] = price_earnings(price, _positive(eps))
    values["Earnings Yield"] = divide(eps, price)
    values["P/B"] = price_to_book(price, _positive(bvps))
    values["Dividend Yield"] = dividend_yield(dps, price)
    values["Payout Ratio"] = payout_ratio(dps, _positive(annual_eps))
    rows.append(
        _ratio(
            ticker,
            "P/E",
            values["P/E"],
            "Current market price / EPS",
            price,
            eps,
            income_label,
            eps_fact,
            notes=_not_meaningful(eps),
        )
    )
    rows.append(
        _ratio(
            ticker,
            "Earnings Yield",
            values["Earnings Yield"],
            "EPS / current market price",
            eps,
            price,
            income_label,
            eps_fact,
        )
    )
    rows.append(
        _ratio(
            ticker,
            "P/B",
            values["P/B"],
            "Current market price / book value per share",
            price,
            bvps,
            f"As at {balance_date}" if balance_date else None,
            *bvps_inputs,
            notes=_not_meaningful(bvps),
        )
    )
    rows.append(
        _ratio(
            ticker,
            "Dividend Yield",
            values["Dividend Yield"],
            "DPS / current market price",
            dps,
            price,
            fy,
            annual.get("dps"),
        )
    )
    rows.append(
        _ratio(
            ticker,
            "Payout Ratio",
            values["Payout Ratio"],
            "DPS / EPS, both for the latest financial year",
            dps,
            annual_eps,
            fy,
            annual.get("dps"),
            annual.get("eps"),
            notes=_not_meaningful(annual_eps),
        )
    )
    values["Income Period Basis"] = income_label
    values["Cash Flow Period Basis"] = cash_label
    values["Balance Sheet Date"] = balance_date
    values["Latest Financial Period"] = (
        snapshot.ttm_label() if snapshot.income_basis == "ttm" else fy
    )
    return values, rows


def _join_notes(*notes: str | None) -> str | None:
    kept = [note for note in notes if note]
    return " ".join(kept) or None
