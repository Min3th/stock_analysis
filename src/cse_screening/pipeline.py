"""End-to-end pilot orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml

from .calculations.screening import (
    SCREEN_COLUMNS,
    Snapshot,
    build_snapshot,
    previous_value,
    screening_metrics,
)
from .corrections import correction_candidates, load_corrections
from .downloaders.announcements import CSEDividendClient, dividend_type
from .downloaders.financials import CSEFinancialDocumentClient
from .downloaders.http import CachedDownloader, get_market_data
from .downloaders.liquidity import LiquidityStore
from .downloaders.universe import CSEUniverseClient, apply_universe_config
from .exporters.workbook import export_all
from .extractors.statements import (
    METRIC_ALIASES,
    extract_document_metrics,
    extract_one_off_indicators,
)
from .parsers.pdf import extract_document
from .validators.extraction import validate_extracted_facts
from .validators.flags import company_flags, sector_relative_flags


def run(
    period: str,
    industry_group: str = "Capital Goods",
    company: str | None = None,
    root: Path = Path("."),
    correction_path: Path | None = None,
) -> dict[str, Path]:
    config = yaml.safe_load((root / "config" / "companies.yml").read_text(encoding="utf-8"))
    pipeline_config = yaml.safe_load(
        (root / "config" / "pipeline.example.yml").read_text(encoding="utf-8")
    )
    configured = {item["ticker"]: item for item in config["companies"]}
    as_of = datetime.now(ZoneInfo("Asia/Colombo")).date()
    group, cse_companies = CSEUniverseClient().companies(industry_group)
    companies, universe_audit = apply_universe_config(
        group, cse_companies, config.get("universe"), as_of
    )
    for issuer in companies:
        if issuer["ticker"] in configured:
            fallback_documents = configured[issuer["ticker"]].get("documents", [])
            issuer["documents"] = [*issuer.get("documents", []), *fallback_documents]
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
        ).discover(companies, as_of)
        for issuer in companies:
            issuer["documents"] = _merge_documents(
                discovered.get(issuer["ticker"], []), issuer.get("documents", [])
            )
    except (httpx.HTTPError, OSError, TypeError, ValueError) as exc:
        financial_discovery_error = f"CSE financial filing discovery: {exc}"
    downloader = CachedDownloader(root / "data" / "raw")
    raw, sources, screening, ratios, history, review, dividends = [], [], [], [], [], [], []
    flag_context: dict[str, dict] = {}
    dividend_error = None
    try:
        dividend_announcements = CSEDividendClient(root / "data" / "raw").latest_for_companies(
            companies
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        dividend_announcements = {}
        dividend_error = f"CSE dividend announcement feed: {exc}"
    thresholds = pipeline_config["flags"]
    liquidity_lookback = int(thresholds.get("liquidity_lookback_trading_days", 20))
    liquidity_store = LiquidityStore(root / "data" / "raw")
    liquidity_store.capture(companies)
    liquidity = liquidity_store.summaries(
        [issuer["ticker"] for issuer in companies], liquidity_lookback
    )
    threshold = Decimal(str(pipeline_config.get("confidence_threshold", "0.8")))
    share_classes: dict[str, int] = {}
    for issuer in companies:
        symbol = issuer["ticker"].split(".", 1)[0]
        share_classes[symbol] = share_classes.get(symbol, 0) + 1

    def usable(fact: dict) -> bool:
        return fact["confidence"] >= threshold

    for issuer in companies:
        document_facts: list[tuple[dict, list[dict]]] = []
        one_off_evidence: list[dict] = []
        document_errors: list[str] = []
        if financial_discovery_error:
            document_errors.append(financial_discovery_error)
        if dividend_error:
            document_errors.append(dividend_error)
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

        price = _decimal(market.get("price"))
        market_cap = _decimal(market.get("market_cap"))
        implied_shares = (market_cap / price).quantize(Decimal(1)) if market_cap and price else None
        multi_class = share_classes[issuer["ticker"].split(".", 1)[0]] > 1
        annual_periods = [
            str(item["period_end"])
            for item in issuer.get("documents", [])
            if item["kind"] == "annual_report"
        ]
        latest_annual_period = max(annual_periods, default=None)
        raw_by_id: dict[str, dict] = {}
        for document in issuer.get("documents", []):
            try:
                path, checksum, cached = downloader.download(
                    issuer["ticker"], document["url"], document["title"]
                )
                parsed = extract_document(path, pipeline_config)
                pages = parsed.pages
                for warning in parsed.warnings:
                    review.append(
                        {
                            "Company": issuer["name"],
                            "Ticker": issuer["ticker"],
                            "Metric": "document_page",
                            "Financial Period": str(document["period_end"]),
                            "Candidate Values": "",
                            "Source Document": document["title"],
                            "Source Page": warning["page"],
                            "Source Text": "",
                            "Extraction Strategy": warning["strategy"],
                            "Validation Rule": "parser_fallback",
                            "Reason for Uncertainty": warning["reason"],
                        }
                    )
                if document["kind"] == "annual_report":
                    for evidence in extract_one_off_indicators(pages):
                        one_off_evidence.append(
                            {
                                **evidence,
                                "document": document["title"],
                                "url": document["url"],
                            }
                        )
                extracted = extract_document_metrics(pages, document["kind"])
                for candidate in extracted:
                    page_method = parsed.methods[candidate["page"] - 1]
                    strategy = candidate.get("extraction_method", "statement_label_line")
                    candidate["extraction_method"] = f"{strategy}+{page_method}"
                for candidate in correction_candidates(corrections, issuer["ticker"], document):
                    extracted.append(candidate)
                    applied_corrections.add(candidate["correction_id"])
                is_latest_annual = (
                    document["kind"] == "annual_report"
                    and str(document["period_end"]) == latest_annual_period
                )
                validation_issues = validate_extracted_facts(
                    extracted,
                    implied_shares=implied_shares if is_latest_annual else None,
                    multi_class=multi_class,
                    check_per_share=is_latest_annual,
                )
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
                        "Parsing Methods": "; ".join(sorted(set(parsed.methods))),
                        "Parser Warnings": len(parsed.warnings),
                    }
                )
                for fact in extracted:
                    fact_suffix = (
                        f":correction:{fact['correction_id']}" if fact.get("correction_id") else ""
                    )
                    fact["fact_id"] = (
                        f"{issuer['ticker']}:{doc_id}:{fact['metric']}:{fact['page']}{fact_suffix}"
                    )
                    fact["period"] = str(document["period_end"])
                    fact["document"] = document["title"]
                    raw_by_id[fact["fact_id"]] = record = {}
                    raw.append(record)
                    record.update(
                        {
                            "Fact ID": fact["fact_id"],
                            "Company": issuer["name"],
                            "Ticker": issuer["ticker"],
                            "Financial Period": str(document["period_end"]),
                            "Period Length": _period_length(fact, document),
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
                            "Statement Scope": fact.get("statement_scope", "unknown"),
                            "Extraction Confidence": fact["confidence"],
                            "Extraction Method": fact.get("extraction_method", "unknown"),
                            "Validation Status": fact.get("validation_status", "not_run"),
                            "Validation Notes": fact.get("validation_notes", ""),
                            "Source Text": fact["source_text"],
                            "Notes": fact.get(
                                "notes",
                                "First matching label in the document; review before use.",
                            ),
                            "Correction ID": fact.get("correction_id"),
                            "Used In Screening": "no",
                        }
                    )
                    history.extend(_history_rows(issuer, document, fact, threshold))
                document_facts.append((document, extracted))
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                document_errors.append(f"{document['title']}: {exc}")

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
        liquidity_summary = liquidity.get(issuer["ticker"], {})
        observations = [item for item in history if item["Ticker"] == issuer["ticker"]]
        market_fact = _market_share_count(
            issuer, document_facts, latest_annual_period, implied_shares, multi_class, usable
        )
        if market_fact is not None:
            raw_by_id[market_fact["fact_id"]] = record = _market_fact_record(issuer, market_fact)
            raw.append(record)
        snapshot = build_snapshot(issuer["ticker"], document_facts, usable)
        metrics, lineage = screening_metrics(snapshot, price, observations)
        for fact in snapshot.annual.values():
            raw_by_id[fact["fact_id"]]["Used In Screening"] = "yes"
        for fact in snapshot.ttm.values():
            for source in fact["inputs"]:
                raw_by_id[source["fact_id"]]["Used In Screening"] = "yes (TTM input)"
        ratios.extend(lineage)
        row = {column: None for column in SCREEN_COLUMNS}
        row.update(metrics)
        row.update(
            {
                "Ticker": issuer["ticker"],
                "Company": issuer["name"],
                "Current Price": price,
                "Market Cap": market_cap,
                "Recent Volume": market.get("share_volume"),
                "Average Daily Volume": liquidity_summary.get("average_volume"),
                "Median Daily Volume": liquidity_summary.get("median_volume"),
                "Liquidity Trading Days": liquidity_summary.get("observations"),
                "Liquidity Period": (
                    f"{liquidity_summary.get('period_start')} to "
                    f"{liquidity_summary.get('period_end')}"
                    if liquidity_summary.get("period_start")
                    else None
                ),
                "Data Confidence": _data_confidence(snapshot, document_facts, threshold),
            }
        )
        if snapshot.annual_end and (as_of - snapshot.annual_end).days > 548:
            row["Data Confidence"] = "review" if row["Data Confidence"] == "high" else "low"
            snapshot.notes.append(
                f"The latest annual report available is for the year to {snapshot.annual_end}; "
                "no later annual report was found, so annual metrics are out of date."
            )
        if snapshot.annual_months != 12 and row["Data Confidence"] == "high":
            row["Data Confidence"] = "review"
        for note in snapshot.notes:
            review.append(
                {
                    "Company": issuer["name"],
                    "Ticker": issuer["ticker"],
                    "Metric": "period_basis",
                    "Financial Period": row["Latest Financial Period"],
                    "Candidate Values": "",
                    "Source Document": "",
                    "Source Page": "",
                    "Source Text": "",
                    "Extraction Strategy": "",
                    "Validation Rule": "period_basis",
                    "Reason for Uncertainty": note,
                }
            )
        total_equity = snapshot.annual_value("total_equity")
        company_flag_list = company_flags(
            row,
            thresholds,
            history=observations,
            total_equity=total_equity,
            one_off_evidence=one_off_evidence,
        )
        if snapshot.annual_months != 12:
            company_flag_list.append(
                f"financial period of {snapshot.annual_months} months (year-end changed)"
            )
        row["Flags"] = "; ".join(company_flag_list)
        flag_context[issuer["ticker"]] = {
            "one_off_evidence": one_off_evidence,
            "total_equity": total_equity,
        }
        sources.append(
            {
                "Company": issuer["name"],
                "Ticker": issuer["ticker"],
                "Document": "CSE daily trading-volume snapshots",
                "Type": "market_liquidity_history",
                "Period End": liquidity_summary.get("period_end"),
                "Source URL": liquidity_summary.get("source_url"),
                "Local Path": str(root / "data" / "raw" / "market_liquidity"),
                "Notes": (
                    f"{liquidity_summary.get('observations', 0)} of "
                    f"{liquidity_lookback} requested trading-day observations"
                ),
            }
        )
        screening.append(row)
        required_metrics = [*METRIC_ALIASES, "total_debt", "ordinary_shares_outstanding"]
        missing = [metric for metric in required_metrics if metric not in snapshot.annual]
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
                    "Reason for Uncertainty": (
                        "No candidate for this metric was found in the latest annual report"
                    ),
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
    relative_flags = sector_relative_flags(screening, thresholds)
    for row in screening:
        existing = [item for item in row["Flags"].split("; ") if item]
        row["Flags"] = "; ".join([*existing, *relative_flags[row["Ticker"]]])

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
    history[:] = _deduplicate_history(history)
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
        _flag_records(screening, flag_context, thresholds),
        review,
        universe_audit,
    )


def _decimal(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _flag_records(rows: list[dict], contexts: dict[str, dict], thresholds: dict) -> list[dict]:
    """Expand the compact screening flags into auditable flag-sheet rows."""
    pe_values = sorted(row["P/E"] for row in rows if row.get("P/E") is not None and row["P/E"] > 0)
    pb_values = sorted(row["P/B"] for row in rows if row.get("P/B") is not None and row["P/B"] > 0)

    def midpoint(values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        middle = len(values) // 2
        return (
            values[middle]
            if len(values) % 2
            else (values[middle - 1] + values[middle]) / Decimal(2)
        )

    pe_median, pb_median = midpoint(pe_values), midpoint(pb_values)
    output = []
    for row in rows:
        context = contexts.get(row["Ticker"], {})
        for flag in (item for item in row.get("Flags", "").split("; ") if item):
            evidence = ""
            source_pages = ""
            source_documents = ""
            source_urls = ""
            if flag == "negative EPS":
                evidence = f"EPS={row.get('EPS')}"
            elif flag.startswith("declining EPS"):
                evidence = "Latest three consecutive annual EPS observations decline"
            elif flag.startswith("declining revenue"):
                evidence = "Latest three consecutive annual revenue observations decline"
            elif flag == "negative operating cash flow":
                evidence = f"Operating Cash Flow={row.get('Operating Cash Flow')}"
            elif flag == "operating cash flow materially below net profit":
                evidence = (
                    f"OCF/Net Profit={row.get('OCF / Net Profit')}; threshold="
                    f"{thresholds.get('ocf_to_net_profit_low', 0.7)}"
                )
            elif flag == "high debt-to-equity":
                evidence = (
                    f"Debt-to-Equity={row.get('Debt-to-Equity')}; threshold="
                    f"{thresholds.get('high_debt_to_equity', 2)}"
                )
            elif flag == "negative equity":
                evidence = f"Total Equity={context.get('total_equity')}"
            elif flag == "dividend payout above 100%":
                evidence = f"Payout Ratio={row.get('Payout Ratio')}"
            elif flag.startswith("P/E unusually"):
                evidence = f"P/E={row.get('P/E')}; positive sector median={pe_median}"
            elif flag.startswith("P/B unusually"):
                evidence = f"P/B={row.get('P/B')}; positive sector median={pb_median}"
            elif "liquidity" in flag:
                evidence = (
                    f"Average daily volume={row.get('Average Daily Volume')}; "
                    f"observations={row.get('Liquidity Trading Days')}; period="
                    f"{row.get('Liquidity Period')}; low-volume threshold="
                    f"{thresholds.get('low_liquidity_average_daily_volume', 10000)}"
                )
            elif flag == "possible one-off profit or loss":
                items = context.get("one_off_evidence", [])
                evidence = " | ".join(item["source_text"] for item in items)
                source_pages = "; ".join(str(item["page"]) for item in items)
                source_documents = "; ".join(item["document"] for item in items)
                source_urls = "; ".join(item["url"] for item in items)
            output.append(
                {
                    "Ticker": row["Ticker"],
                    "Company": row["Company"],
                    "Flag": flag,
                    "Evidence": evidence,
                    "Source Documents": source_documents,
                    "Source URLs": source_urls,
                    "Source Pages": source_pages,
                }
            )
    return output


def _period_length(fact: dict, document: dict) -> str | None:
    """Human-readable length of the period a flow fact covers."""
    months = fact.get("period_months")
    if months == 0:
        return "year to date"
    if months:
        return f"{months} months"
    return "12 months" if document["kind"] == "annual_report" else None


HISTORY_METRICS = {"revenue", "net_profit", "eps", "total_equity", "dps", "operating_cash_flow"}


CORE_METRICS = (
    "revenue",
    "net_profit",
    "eps",
    "total_assets",
    "total_equity",
    "operating_cash_flow",
)


def _data_confidence(
    snapshot: Snapshot, document_facts: list[tuple[dict, list[dict]]], threshold: Decimal
) -> str:
    """Summarise how much of the latest annual report passed validation.

    ``high``: every core metric is usable and nothing in the latest annual
    report is under review. ``review``: some values were withheld or flagged.
    ``low``: fewer than half of the core metrics are usable.
    """
    core = sum(metric in snapshot.annual for metric in CORE_METRICS)
    if core < len(CORE_METRICS) / 2:
        return "low"
    latest = [
        facts
        for document, facts in document_facts
        if document["kind"] == "annual_report"
        and snapshot.annual_end is not None
        and str(document["period_end"]) == snapshot.annual_end.isoformat()
    ]
    flagged = any(
        fact["confidence"] < threshold or fact.get("validation_status") == "review"
        for facts in latest
        for fact in facts
        if fact["metric"] in CORE_METRICS
    )
    return "high" if core == len(CORE_METRICS) and not flagged else "review"


def _market_share_count(
    issuer: dict,
    document_facts: list[tuple[dict, list[dict]]],
    latest_annual_period: str | None,
    implied_shares: Decimal | None,
    multi_class: bool,
    usable,
) -> dict | None:
    """Add the CSE-implied share count when the annual report gives no usable one.

    The count is market capitalisation divided by the last traded price for the
    listed class. It is not used for an issuer with more than one listed class,
    because one class is not the whole ordinary share base.
    """
    if implied_shares is None or multi_class or latest_annual_period is None:
        return None
    for document, facts in document_facts:
        if document["kind"] != "annual_report":
            continue
        if str(document["period_end"]) != latest_annual_period:
            continue
        reported = [fact for fact in facts if fact["metric"] == "ordinary_shares_outstanding"]
        if any(usable(fact) for fact in reported):
            return None
        market = issuer.get("market_data") or {}
        fact = {
            "metric": "ordinary_shares_outstanding",
            "value": implied_shares,
            "original_value": implied_shares,
            "unit": "shares",
            "original_unit": "shares",
            "multiplier": Decimal(1),
            "page": None,
            "source_text": "CSE market capitalisation / last traded price",
            "confidence": Decimal("0.85"),
            "comparatives": [implied_shares],
            "extraction_method": "cse_market_data_implied_share_count",
            "statement_scope": "listed class",
            "fact_id": f"{issuer['ticker']}:market:ordinary_shares_outstanding",
            "period": latest_annual_period,
            "source_url": market.get("market_source_url"),
            "validation_status": "passed",
            "notes": (
                "Current shares in issue implied by CSE market data, used because the "
                "annual report gave no share count that passed reconciliation. It is a "
                "current count, not the count at the balance-sheet date."
            ),
        }
        facts.append(fact)
        return fact
    return None


def _market_fact_record(issuer: dict, fact: dict) -> dict:
    return {
        "Fact ID": fact["fact_id"],
        "Company": issuer["name"],
        "Ticker": issuer["ticker"],
        "Financial Period": fact["period"],
        "Period Length": None,
        "Metric": fact["metric"],
        "Extracted Value": fact["value"],
        "Unit": fact["unit"],
        "Original Value": fact["original_value"],
        "Original Unit": fact["original_unit"],
        "Scale Multiplier": fact["multiplier"],
        "Source Document": "CSE market data",
        "Source URL": fact.get("source_url"),
        "Source Page": None,
        "Annual/Interim": "market_data",
        "Statement Scope": fact["statement_scope"],
        "Extraction Confidence": fact["confidence"],
        "Extraction Method": fact["extraction_method"],
        "Validation Status": fact["validation_status"],
        "Validation Notes": "",
        "Source Text": fact["source_text"],
        "Notes": fact["notes"],
        "Correction ID": None,
        "Used In Screening": "no",
    }


def _history_rows(issuer: dict, document: dict, fact: dict, threshold: Decimal) -> list[dict]:
    """Annual history observations from a statement's current and comparative columns."""
    if (
        document["kind"] != "annual_report"
        or fact["metric"] not in HISTORY_METRICS
        or fact["confidence"] < threshold
        or fact.get("period_months") not in (None, 12)
    ):
        return []
    period_end = document["period_end"]
    if not isinstance(period_end, date):
        period_end = date.fromisoformat(str(period_end))
    observations = [(0, fact["value"], "reported current")]
    previous = previous_value(fact)
    # A comparative under 1% of the current value is a different column (for
    # example a % change), not the prior year.
    if previous is not None and abs(previous) >= abs(fact["value"]) * Decimal("0.01"):
        observations.append((1, previous, "reported comparative"))
    return [
        {
            "Ticker": issuer["ticker"],
            "Company": issuer["name"],
            "Financial Year End": str(_prior_year_end(period_end, offset)),
            "Metric": fact["metric"],
            "Value": value,
            "Unit": fact["unit"],
            "Source Document": document["title"],
            "Source URL": document["url"],
            "Source Page": fact["page"],
            "Confidence": fact["confidence"],
            "Value Basis": basis,
            "Source Period End": str(period_end),
            "Correction ID": fact.get("correction_id"),
        }
        for offset, value, basis in observations
    ]


def _prior_year_end(period_end: date, offset: int) -> date:
    try:
        return period_end.replace(year=period_end.year - offset)
    except ValueError:
        return period_end.replace(year=period_end.year - offset, day=28)


def _deduplicate_history(rows: list[dict]) -> list[dict]:
    """Prefer direct current-year observations over overlapping comparatives."""
    selected = {}
    for row in rows:
        key = (row["Ticker"], row["Metric"], row["Financial Year End"])
        rank = (
            bool(row.get("Correction ID")),
            row.get("Value Basis") == "reported current",
            str(row.get("Source Period End") or ""),
            row.get("Confidence", Decimal(0)),
        )
        prior = selected.get(key)
        if prior is None:
            selected[key] = row
            continue
        prior_rank = (
            bool(prior.get("Correction ID")),
            prior.get("Value Basis") == "reported current",
            str(prior.get("Source Period End") or ""),
            prior.get("Confidence", Decimal(0)),
        )
        if rank > prior_rank:
            selected[key] = row
    return sorted(
        selected.values(),
        key=lambda item: (item["Ticker"], item["Metric"], item["Financial Year End"]),
        reverse=True,
    )


def _merge_documents(discovered: list[dict], configured: list[dict]) -> list[dict]:
    """Retain three annual periods and the latest interim, preferring official discovery."""
    unique = {}
    for document in [*configured, *discovered]:
        unique[document["url"]] = document
    selected = []
    for kind in ("annual_report", "interim_statement"):
        candidates = [item for item in unique.values() if item["kind"] == kind]
        limit = 3 if kind == "annual_report" else 1
        by_period = {}
        for item in candidates:
            key = str(item.get("period_end") or "")
            prior = by_period.get(key)
            rank = (
                str(item.get("publication_date") or ""),
                bool(item.get("discovery_url")),
            )
            if prior is None or rank > (
                str(prior.get("publication_date") or ""),
                bool(prior.get("discovery_url")),
            ):
                by_period[key] = item
        selected.extend(by_period[key] for key in sorted(by_period, reverse=True)[:limit])
    return selected
