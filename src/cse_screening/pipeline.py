"""End-to-end pilot orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml

from .calculations.ratios import (
    debt_to_equity,
    divide,
    dividend_yield,
    free_cash_flow,
    net_debt,
    payout_ratio,
    price_earnings,
    price_to_book,
    roa,
    roe,
)
from .corrections import correction_candidates, load_corrections
from .downloaders.announcements import CSEDividendClient, dividend_type
from .downloaders.financials import CSEFinancialDocumentClient
from .downloaders.http import CachedDownloader, get_market_data
from .downloaders.universe import CSEUniverseClient
from .exporters.workbook import export_all
from .extractors.statements import (
    METRIC_ALIASES,
    extract_cash_equivalents,
    extract_interim_flow_metrics,
    extract_metrics,
    extract_retained_earnings_note,
    extract_total_debt,
)
from .parsers.pdf import extract_pages
from .periods import TTM_FLOW_METRICS, ttm_from_annual_and_ytd
from .validators.extraction import validate_extracted_facts
from .validators.flags import company_flags

SCREEN_COLUMNS = [
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
    "Retained Earnings",
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
]


def run(
    period: str,
    industry_group: str = "Capital Goods",
    company: str | None = None,
    root: Path = Path("."),
    correction_path: Path | None = None,
) -> dict[str, Path]:
    config = yaml.safe_load((root / "config" / "companies.yml").read_text(encoding="utf-8"))
    configured = {item["ticker"]: item for item in config["companies"]}
    group, companies = CSEUniverseClient().companies(industry_group)
    for issuer in companies:
        if issuer["ticker"] in configured:
            market_data = issuer["market_data"]
            issuer.update(configured[issuer["ticker"]])
            issuer["market_data"] = market_data
    if company:
        companies = [item for item in companies if item["ticker"] == company]
        if not companies:
            raise ValueError(f"Ticker {company!r} is not in the selected CSE industry group")
    if correction_path is None:
        correction_path = root / "config" / "corrections.yml"
    elif not correction_path.is_absolute():
        correction_path = root / correction_path
    corrections = load_corrections(correction_path)
    applied_corrections: set[str] = set()
    financial_discovery_error = None
    financial_feed_cached = False
    try:
        discovered, financial_feed_cached = CSEFinancialDocumentClient(
            root / "data" / "raw"
        ).discover(companies, datetime.now(ZoneInfo("Asia/Colombo")).date())
        for issuer in companies:
            issuer["documents"] = _merge_documents(
                discovered.get(issuer["ticker"], []), issuer.get("documents", [])
            )
    except (httpx.HTTPError, OSError, TypeError, ValueError) as exc:
        financial_discovery_error = f"CSE financial filing discovery: {exc}"
    downloader = CachedDownloader(root / "data" / "raw")
    raw, sources, screening, ratios, history, review, dividends = [], [], [], [], [], [], []
    dividend_error = None
    try:
        dividend_announcements = CSEDividendClient(root / "data" / "raw").latest_for_companies(
            companies
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        dividend_announcements = {}
        dividend_error = f"CSE dividend announcement feed: {exc}"
    thresholds = yaml.safe_load((root / "config" / "pipeline.example.yml").read_text())["flags"]
    for issuer in companies:
        facts: dict[str, dict] = {}
        annual_facts: dict[str, dict] = {}
        document_facts: list[tuple[dict, list[dict]]] = []
        document_errors: list[str] = []
        if financial_discovery_error:
            document_errors.append(financial_discovery_error)
        if dividend_error:
            document_errors.append(dividend_error)
        for document in issuer.get("documents", []):
            try:
                path, checksum, cached = downloader.download(
                    issuer["ticker"], document["url"], document["title"]
                )
                pages = extract_pages(path)
                extracted = extract_metrics(pages)
                for candidate in extracted:
                    candidate.setdefault("extraction_method", "statement_label_line")
                if document["kind"] == "interim_statement":
                    for candidate in extract_interim_flow_metrics(pages):
                        candidate["extraction_method"] = "interim_same_scope_columns"
                        existing = next(
                            (item for item in extracted if item["metric"] == candidate["metric"]),
                            None,
                        )
                        if existing is not None:
                            extracted.remove(existing)
                        extracted.append(candidate)
                specialized = (
                    (extract_total_debt(pages), "debt_component_aggregation"),
                    (extract_cash_equivalents(pages), "cash_component_aggregation"),
                    (extract_retained_earnings_note(pages), "retained_earnings_note"),
                )
                for candidate, method in specialized:
                    if candidate is None:
                        continue
                    candidate["extraction_method"] = method
                    existing = next(
                        (item for item in extracted if item["metric"] == candidate["metric"]), None
                    )
                    if existing is None:
                        extracted.append(candidate)
                    elif candidate["confidence"] > existing["confidence"]:
                        extracted.remove(existing)
                        extracted.append(candidate)
                for candidate in correction_candidates(corrections, issuer["ticker"], document):
                    extracted.append(candidate)
                    applied_corrections.add(candidate["correction_id"])
                validation_issues = validate_extracted_facts(extracted)
                for issue in validation_issues:
                    review.append(
                        {
                            "Company": issuer["name"],
                            "Ticker": issuer["ticker"],
                            "Metric": issue["metric"],
                            "Financial Period": str(document["period_end"]),
                            "Candidate Values": issue["candidate_values"],
                            "Source Document": document["title"],
                            "Source Page": issue["source_page"],
                            "Source Text": issue["source_text"],
                            "Extraction Strategy": issue["strategy"],
                            "Validation Rule": issue["rule"],
                            "Reason for Uncertainty": issue["reason"],
                        }
                    )
                doc_id = checksum[:16]
                sources.append(
                    {
                        "Company": issuer["name"],
                        "Ticker": issuer["ticker"],
                        "Document ID": doc_id,
                        "Document": document["title"],
                        "Type": document["kind"],
                        "Publication Date": document["publication_date"],
                        "Period End": document["period_end"],
                        "Source URL": document["url"],
                        "Discovery URL": document.get("discovery_url"),
                        "Announcement ID": document.get("announcement_id"),
                        "Local Path": str(path),
                        "SHA256": checksum,
                        "Retrieved UTC": datetime.now(UTC).isoformat(),
                        "Cache Hit": cached,
                        "Discovery Cache Hit": financial_feed_cached
                        if document.get("discovery_url")
                        else None,
                    }
                )
                for fact in extracted:
                    fact_suffix = (
                        f":correction:{fact['correction_id']}" if fact.get("correction_id") else ""
                    )
                    record = {
                        "Fact ID": f"{issuer['ticker']}:{doc_id}:{fact['metric']}:{fact['page']}{fact_suffix}",
                        "Company": issuer["name"],
                        "Ticker": issuer["ticker"],
                        "Financial Period": str(document["period_end"]),
                        "Metric": fact["metric"],
                        "Extracted Value": fact["value"],
                        "Unit": fact["unit"],
                        "Original Value": fact["original_value"],
                        "Original Unit": fact["original_unit"],
                        "Scale Multiplier": fact["multiplier"],
                        "Source Document": document["title"],
                        "Source URL": document["url"],
                        "Source Page": fact["page"],
                        "Annual/Interim": document["kind"],
                        "Extraction Confidence": fact["confidence"],
                        "Extraction Method": fact.get("extraction_method", "unknown"),
                        "Validation Status": fact.get("validation_status", "not_run"),
                        "Validation Notes": fact.get("validation_notes", ""),
                        "Source Text": fact["source_text"],
                        "Notes": fact.get(
                            "notes",
                            "First matching consolidated-statement candidate; review before investment use.",
                        ),
                        "Correction ID": fact.get("correction_id"),
                        "Statement Scope": fact.get("statement_scope"),
                    }
                    raw.append(record)
                    if (
                        document["kind"] == "annual_report"
                        and fact["metric"]
                        in {
                            "revenue",
                            "net_profit",
                            "eps",
                            "total_equity",
                            "dps",
                            "operating_cash_flow",
                        }
                        and fact["confidence"] >= Decimal("0.8")
                    ):
                        year = document["period_end"].year
                        if fact.get("correction_id"):
                            history[:] = [
                                item
                                for item in history
                                if not (
                                    item["Ticker"] == issuer["ticker"]
                                    and item["Metric"] == fact["metric"]
                                    and item["Financial Year End"] == f"{year}-03-31"
                                )
                            ]
                        # Later columns may switch from Group to Company scope.
                        comparable_values = fact["comparatives"][:2]
                        if len(comparable_values) == 2 and abs(comparable_values[1]) < abs(
                            comparable_values[0]
                        ) * Decimal("0.01"):
                            comparable_values = comparable_values[:1]
                        for offset, historical_value in enumerate(comparable_values):
                            history.append(
                                {
                                    "Ticker": issuer["ticker"],
                                    "Company": issuer["name"],
                                    "Financial Year End": f"{year - offset}-03-31",
                                    "Metric": fact["metric"],
                                    "Value": historical_value * fact["multiplier"],
                                    "Unit": fact["unit"],
                                    "Source Document": document["title"],
                                    "Source URL": document["url"],
                                    "Source Page": fact["page"],
                                    "Confidence": fact["confidence"],
                                }
                            )
                    # Latest documents win; low-confidence candidates do not silently replace stronger facts.
                    prior = facts.get(fact["metric"])
                    if prior is None or (str(document["period_end"]), fact["confidence"]) > (
                        prior["period"],
                        prior["confidence"],
                    ):
                        facts[fact["metric"]] = {
                            **fact,
                            "period": str(document["period_end"]),
                            "fact_id": record["Fact ID"],
                        }
                    if document["kind"] == "annual_report":
                        prior_annual = annual_facts.get(fact["metric"])
                        if prior_annual is None or (
                            str(document["period_end"]),
                            fact["confidence"],
                        ) > (prior_annual["period"], prior_annual["confidence"]):
                            annual_facts[fact["metric"]] = {
                                **fact,
                                "period": str(document["period_end"]),
                                "fact_id": record["Fact ID"],
                            }
                document_facts.append((document, extracted))
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                document_errors.append(f"{document['title']}: {exc}")

        ttm_facts, ttm_rows = _construct_ttm_facts(issuer, annual_facts, document_facts)
        for metric, fact in ttm_facts.items():
            facts[metric] = fact
        ratios.extend(ttm_rows)

        for announcement in dividend_announcements.get(issuer["ticker"], []):
            base = announcement.get("reqBaseAnnouncement", {})
            docs = announcement.get("reqAnnouncementDocs", [])
            source_urls = []
            for attachment in docs:
                source_url = (
                    f"{attachment.get('baseUrl', 'https://cdn.cse.lk/')}{attachment['fileUrl']}"
                )
                source_urls.append(source_url)
                try:
                    path, checksum, cached = downloader.download(
                        issuer["ticker"], source_url, attachment.get("fileOriginalName", "Dividend")
                    )
                    sources.append(
                        {
                            "Company": issuer["name"],
                            "Ticker": issuer["ticker"],
                            "Document ID": checksum[:16],
                            "Document": attachment.get("fileOriginalName")
                            or attachment.get("fileName"),
                            "Type": "dividend_announcement",
                            "Publication Date": base.get("dateOfAnnouncement"),
                            "Period End": base.get("financialYear"),
                            "Source URL": source_url,
                            "Local Path": str(path),
                            "SHA256": checksum,
                            "Retrieved UTC": datetime.now(UTC).isoformat(),
                            "Cache Hit": cached,
                        }
                    )
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    document_errors.append(f"dividend attachment {source_url}: {exc}")
            dividends.append(
                {
                    "Ticker": issuer["ticker"],
                    "Company": issuer["name"],
                    "Announcement ID": base.get("id"),
                    "Announcement Date": base.get("dateOfAnnouncement"),
                    "Dividend Type": dividend_type(base),
                    "Financial Year": base.get("financialYear"),
                    "Voting DPS": _decimal(base.get("votingDivPerShare")),
                    "Non-Voting DPS": _decimal(base.get("nonVotingDivPerShare")),
                    "Shareholder Approval": base.get("shrHolderApproval"),
                    "AGM Date": base.get("agm"),
                    "XD Date": base.get("xd"),
                    "Record Date": datetime.fromtimestamp(base["recordDate"] / 1000, UTC).date()
                    if base.get("recordDate")
                    else None,
                    "Payment Date": base.get("payment"),
                    "Remarks": base.get("remarks"),
                    "Source URL": "; ".join(source_urls),
                    "API Source": f"https://www.cse.lk/api/getAnnouncementById?announcementId={base.get('id')}",
                    "Detail Cache Hit": announcement.get("_cache_hit"),
                }
            )
        market = issuer.get("market_data")
        try:
            if market is None:
                market = get_market_data(issuer["ticker"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            market = {
                "price": None,
                "market_cap": None,
                "share_volume": None,
                "quantity_issued": None,
            }
            document_errors.append(f"market data: {exc}")

        def value(key: str, fact_map: dict[str, dict] = facts):
            return fact_map.get(key, {}).get("value")

        price = _decimal(market.get("price"))
        eps, bvps, dps = value("eps"), value("bvps"), value("dps")

        def annual_value(key: str, fact_map: dict[str, dict] = annual_facts):
            return fact_map.get(key, {}).get("value")

        def annual_comparative(key: str, fact_map: dict[str, dict] = annual_facts):
            fact = fact_map.get(key, {})
            values = fact.get("comparatives", [])
            return values[1] * fact.get("multiplier", Decimal(1)) if len(values) >= 2 else None

        equity_metric = (
            "ordinary_equity" if annual_value("ordinary_equity") is not None else "total_equity"
        )
        profit_metric = (
            "net_profit_attributable"
            if annual_value("net_profit_attributable") is not None
            else "net_profit"
        )
        ordinary_equity = annual_value(equity_metric)
        ordinary_equity_previous = annual_comparative(equity_metric)
        annual_profit_attributable = annual_value(profit_metric)
        total_debt = annual_value("total_debt")
        annual_ocf = annual_value("operating_cash_flow")
        annual_capex = annual_value("capital_expenditure")
        row = {column: None for column in SCREEN_COLUMNS}
        row.update(
            {
                "Ticker": issuer["ticker"],
                "Company": issuer["name"],
                "Current Price": price,
                "Market Cap": _decimal(market.get("market_cap")),
                "Revenue": value("revenue"),
                "Net Profit": value("net_profit"),
                "EPS": eps,
                "ROE": roe(annual_profit_attributable, ordinary_equity, ordinary_equity_previous),
                "ROA": roa(
                    annual_value("net_profit"),
                    annual_value("total_assets"),
                    annual_comparative("total_assets"),
                ),
                "Debt-to-Equity": debt_to_equity(total_debt, ordinary_equity),
                "Net Debt": net_debt(total_debt, annual_value("cash")),
                "Retained Earnings": annual_value("retained_earnings"),
                "Operating Cash Flow": annual_ocf,
                "Free Cash Flow": free_cash_flow(annual_ocf, annual_capex),
                "OCF / Net Profit": divide(annual_ocf, annual_value("net_profit")),
                "P/E": price_earnings(price, eps),
                "P/B": price_to_book(price, bvps),
                "DPS": dps,
                "Dividend Yield": dividend_yield(dps, price),
                "Payout Ratio": payout_ratio(dps, eps),
                "Earnings Yield": (eps / price if eps is not None and price else None),
                "Latest Financial Period": max((v["period"] for v in facts.values()), default=None),
                "Recent Volume": market.get("share_volume"),
                "Data Confidence": "high"
                if len(facts) >= 8
                and all(v["confidence"] >= Decimal("0.8") for v in facts.values())
                else "review",
            }
        )
        _add_growth_metrics(row, issuer["ticker"], history)
        row["Flags"] = "; ".join(company_flags(row, thresholds))
        screening.append(row)
        for metric in ("P/E", "P/B", "Dividend Yield", "Payout Ratio", "Earnings Yield"):
            input_names = {
                "P/E": ("Current Price", "EPS"),
                "P/B": ("Current Price", "bvps"),
                "Dividend Yield": ("DPS", "Current Price"),
                "Payout Ratio": ("DPS", "EPS"),
                "Earnings Yield": ("EPS", "Current Price"),
            }[metric]
            ratios.append(
                {
                    "Ticker": issuer["ticker"],
                    "Metric": metric,
                    "Value": row[metric],
                    "Formula": f"{input_names[0]} / {input_names[1]}",
                    "Numerator": row.get(input_names[0])
                    if input_names[0] in row
                    else value(input_names[0]),
                    "Denominator": row.get(input_names[1])
                    if input_names[1] in row
                    else value(input_names[1]),
                    "Input Fact IDs": "; ".join(
                        v["fact_id"]
                        for k, v in facts.items()
                        if k in {x.lower() for x in input_names}
                    ),
                    "Source Pages": "; ".join(
                        str(v["page"])
                        for k, v in facts.items()
                        if k in {x.lower() for x in input_names}
                    ),
                }
            )
        calculation_specs = [
            (
                "ROE",
                row["ROE"],
                "Net profit attributable / average ordinary equity",
                annual_profit_attributable,
                (ordinary_equity + ordinary_equity_previous) / Decimal(2)
                if ordinary_equity is not None and ordinary_equity_previous is not None
                else None,
                (profit_metric, equity_metric),
            ),
            (
                "ROA",
                row["ROA"],
                "Net profit / average total assets",
                annual_value("net_profit"),
                (annual_value("total_assets") + annual_comparative("total_assets")) / Decimal(2)
                if annual_value("total_assets") is not None
                and annual_comparative("total_assets") is not None
                else None,
                ("net_profit", "total_assets"),
            ),
            (
                "Debt-to-Equity",
                row["Debt-to-Equity"],
                "Total debt / ordinary equity",
                total_debt,
                ordinary_equity,
                ("total_debt", equity_metric),
            ),
            (
                "Net Debt",
                row["Net Debt"],
                "Total debt - cash and cash equivalents",
                total_debt,
                annual_value("cash"),
                ("total_debt", "cash"),
            ),
            (
                "Free Cash Flow",
                row["Free Cash Flow"],
                "Operating cash flow - absolute capex",
                annual_ocf,
                annual_capex,
                ("operating_cash_flow", "capital_expenditure"),
            ),
            (
                "OCF / Net Profit",
                row["OCF / Net Profit"],
                "Operating cash flow / net profit",
                annual_ocf,
                annual_value("net_profit"),
                ("operating_cash_flow", "net_profit"),
            ),
        ]
        for metric, result, formula, numerator, denominator, input_metrics in calculation_specs:
            input_facts = [annual_facts[name] for name in input_metrics if name in annual_facts]
            ratios.append(
                {
                    "Ticker": issuer["ticker"],
                    "Metric": metric,
                    "Value": result,
                    "Formula": formula,
                    "Numerator": numerator,
                    "Denominator": denominator,
                    "Input Fact IDs": "; ".join(item["fact_id"] for item in input_facts),
                    "Source Pages": "; ".join(str(item["page"]) for item in input_facts),
                    "Period Basis": max((item["period"] for item in input_facts), default=None),
                }
            )
        missing = [metric for metric in METRIC_ALIASES if metric not in facts]
        if not issuer.get("documents"):
            document_errors.append(
                "No official financial document URLs are configured yet; market data only"
            )
        for metric in missing:
            review.append(
                {
                    "Company": issuer["name"],
                    "Ticker": issuer["ticker"],
                    "Metric": metric,
                    "Financial Period": row["Latest Financial Period"],
                    "Candidate Values": "",
                    "Source Document": "",
                    "Source Page": "",
                    "Source Text": "",
                    "Extraction Strategy": "",
                    "Validation Rule": "missing_metric",
                    "Reason for Uncertainty": "No reliable label/number candidate found",
                }
            )
        for error in document_errors:
            review.append(
                {
                    "Company": issuer["name"],
                    "Ticker": issuer["ticker"],
                    "Metric": "document",
                    "Financial Period": "",
                    "Candidate Values": "",
                    "Source Document": "",
                    "Source Page": "",
                    "Source Text": "",
                    "Extraction Strategy": "",
                    "Validation Rule": "document_error",
                    "Reason for Uncertainty": error,
                }
            )
    selected_tickers = {item["ticker"] for item in companies}
    unapplied = [
        item["id"]
        for item in corrections
        if item.get("status", "active") == "active"
        and item["ticker"] in selected_tickers
        and str(item["id"]) not in applied_corrections
    ]
    if unapplied:
        raise ValueError(
            "Active corrections did not match a configured document exactly: "
            + ", ".join(map(str, unapplied))
        )
    return export_all(
        period,
        group["industry_group"],
        root / "reports",
        screening,
        raw,
        ratios,
        history,
        dividends,
        sources,
        [{"Ticker": row["Ticker"], "Flags": row["Flags"]} for row in screening],
        review,
    )


def _decimal(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _merge_documents(discovered: list[dict], configured: list[dict]) -> list[dict]:
    """Prefer the latest period per kind while retaining configured fallbacks."""
    unique = {}
    for document in [*configured, *discovered]:
        unique[document["url"]] = document
    selected = []
    for kind in ("annual_report", "interim_statement"):
        candidates = [item for item in unique.values() if item["kind"] == kind]
        if candidates:
            selected.append(
                max(
                    candidates,
                    key=lambda item: (
                        str(item.get("period_end") or ""),
                        str(item.get("publication_date") or ""),
                        bool(item.get("discovery_url")),
                    ),
                )
            )
    return selected


def _construct_ttm_facts(
    issuer: dict, annual_facts: dict[str, dict], document_facts: list[tuple[dict, list[dict]]]
) -> tuple[dict[str, dict], list[dict]]:
    """Build traceable TTM flows only from explicitly described compatible YTD data."""
    output: dict[str, dict] = {}
    lineage: list[dict] = []
    annual_documents = [
        document for document, _ in document_facts if document["kind"] == "annual_report"
    ]
    if not annual_documents:
        return output, lineage
    annual_document = max(annual_documents, key=lambda item: str(item["period_end"]))
    annual_end = date.fromisoformat(str(annual_document["period_end"]))
    for document, extracted in document_facts:
        if document["kind"] != "interim_statement" or not document.get("period_months"):
            continue
        current_end = date.fromisoformat(str(document["period_end"]))
        prior_end_value = document.get("comparative_period_end")
        if not prior_end_value:
            continue
        prior_end = date.fromisoformat(str(prior_end_value))
        months = int(document["period_months"])
        for current in extracted:
            metric = current["metric"]
            annual = annual_facts.get(metric)
            comparatives = current.get("comparatives", [])
            if metric not in TTM_FLOW_METRICS or annual is None or len(comparatives) < 2:
                continue
            prior_ytd = comparatives[1] * current.get("multiplier", Decimal(1))
            result = ttm_from_annual_and_ytd(
                annual["value"],
                current["value"],
                prior_ytd,
                annual_end=annual_end,
                current_end=current_end,
                prior_end=prior_end,
                months=months,
            )
            if result is None:
                continue
            period = f"TTM ended {current_end.isoformat()}"
            fact_id = f"{issuer['ticker']}:TTM:{metric}:{current_end.isoformat()}"
            output[metric] = {
                **current,
                "value": result,
                "period": period,
                "fact_id": fact_id,
                "confidence": min(annual["confidence"], current["confidence"]),
                "notes": "Calculated as latest FY + current YTD - prior comparable YTD.",
            }
            lineage.append(
                {
                    "Ticker": issuer["ticker"],
                    "Metric": f"{metric} (TTM)",
                    "Value": result,
                    "Formula": "Latest FY + current YTD - prior comparable YTD",
                    "Numerator": annual["value"],
                    "Denominator": None,
                    "Current YTD": current["value"],
                    "Prior YTD": prior_ytd,
                    "Input Fact IDs": f"{annual['fact_id']}; interim:{metric}:{current_end.isoformat()}",
                    "Source Pages": f"{annual['page']}; {current['page']}",
                    "Period Basis": period,
                }
            )
    return output, lineage


def _add_growth_metrics(row: dict, ticker: str, history: list[dict]) -> None:
    from .calculations.ratios import cagr, growth

    def values(metric: str) -> list[Decimal]:
        return [
            item["Value"]
            for item in history
            if item["Ticker"] == ticker and item["Metric"] == metric
        ]

    revenues, eps_values, profits = values("revenue"), values("eps"), values("net_profit")
    row["Revenue Growth YoY"] = growth(*revenues[:2]) if len(revenues) >= 2 else None
    row["EPS Growth YoY"] = growth(*eps_values[:2]) if len(eps_values) >= 2 else None
    row["Net Profit Growth YoY"] = growth(*profits[:2]) if len(profits) >= 2 else None
    row["3Y Revenue CAGR"] = cagr(revenues[0], revenues[2], 2) if len(revenues) >= 3 else None
    row["3Y EPS CAGR"] = cagr(eps_values[0], eps_values[2], 2) if len(eps_values) >= 3 else None
