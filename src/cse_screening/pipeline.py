"""End-to-end pilot orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import yaml

from .calculations.ratios import dividend_yield, payout_ratio, price_earnings, price_to_book
from .downloaders.http import CachedDownloader, get_market_data
from .exporters.workbook import export_all
from .extractors.statements import METRIC_ALIASES, extract_metrics
from .parsers.pdf import extract_pages
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


def run(period: str, company: str | None = None, root: Path = Path(".")) -> dict[str, Path]:
    config = yaml.safe_load((root / "config" / "companies.yml").read_text(encoding="utf-8"))
    companies = config["companies"]
    if company:
        companies = [item for item in companies if item["ticker"] == company]
        if not companies:
            raise ValueError(f"Ticker {company!r} is not configured")
    downloader = CachedDownloader(root / "data" / "raw")
    raw, sources, screening, ratios, history, review = [], [], [], [], [], []
    thresholds = yaml.safe_load((root / "config" / "pipeline.example.yml").read_text())["flags"]
    for issuer in companies:
        facts: dict[str, dict] = {}
        document_errors: list[str] = []
        for document in issuer.get("documents", []):
            try:
                path, checksum, cached = downloader.download(
                    issuer["ticker"], document["url"], document["title"]
                )
                pages = extract_pages(path)
                extracted = extract_metrics(pages)
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
                        "Local Path": str(path),
                        "SHA256": checksum,
                        "Retrieved UTC": datetime.now(UTC).isoformat(),
                        "Cache Hit": cached,
                    }
                )
                for fact in extracted:
                    record = {
                        "Fact ID": f"{issuer['ticker']}:{doc_id}:{fact['metric']}:{fact['page']}",
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
                        "Source Text": fact["source_text"],
                        "Notes": "First matching consolidated-statement candidate; review before investment use.",
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
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                document_errors.append(f"{document['title']}: {exc}")
        try:
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
                "Operating Cash Flow": value("operating_cash_flow"),
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
        missing = [metric for metric in METRIC_ALIASES if metric not in facts]
        for metric in missing:
            review.append(
                {
                    "Company": issuer["name"],
                    "Ticker": issuer["ticker"],
                    "Metric": metric,
                    "Financial Period": row["Latest Financial Period"],
                    "Candidate Values": "",
                    "Source Page": "",
                    "Source Text": "",
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
                    "Source Page": "",
                    "Source Text": "",
                    "Reason for Uncertainty": error,
                }
            )
    return export_all(
        period,
        root / "reports",
        screening,
        raw,
        ratios,
        history,
        [],
        sources,
        [{"Ticker": row["Ticker"], "Flags": row["Flags"]} for row in screening],
        review,
    )


def _decimal(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


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
