"""Discover a current industry-group universe from the official CSE GICS APIs."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

CSE_API = "https://www.cse.lk/api"
GICS_PAGE = "https://www.cse.lk/listed-entities/gics-classification"

SUPPORTED_INDUSTRY_GROUPS = (
    "Energy",
    "Materials",
    "Capital Goods",
    "Commercial & Professional Services",
    "Transportation",
    "Automobiles & Components",
    "Consumer Durables & Apparel",
    "Consumer Services",
    "Retailing",
    "Food & Staples Retailing",
    "Food, Beverage & Tobacco",
    "Household & Personal Products",
    "Health Care Equipment & Services",
    "Banks",
    "Diversified Financials",
    "Insurance",
    "Software & Services",
    "Telecommunication Services",
    "Utilities",
    "Real Estate Management & Development",
    "Technology Hardware & Equipment",
    "Pharmaceuticals, Biotechnology & Life Sciences",
)

CURRENT_NAME_ALIASES = {
    "real estate management & development": "real estate",
    # CSE currently publishes the Information Technology group under this newer
    # label. The endpoint presently returns no constituents for either label.
    "software & services": "technology hardware & equipment",
}


def normalize_group_name(value: str) -> str:
    value = re.sub(r"^S&P/CSE\s+", "", value.strip(), flags=re.IGNORECASE)
    value = re.sub(r"\s*&\s*", " & ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return re.sub(r"\s+", " ", value).casefold()


class CSEUniverseClient:
    def __init__(self, timeout: float = 30) -> None:
        self.timeout = timeout

    def _post(self, endpoint: str, data: dict | None = None) -> Any:
        response = httpx.post(
            f"{CSE_API}/{endpoint}",
            data=data,
            headers={"User-Agent": "cse-screening-research/0.2"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def industry_groups(self) -> list[dict]:
        sectors = self._post("GICSSectors").get("gicsSectors", [])
        groups = []
        for sector in sectors:
            for group in self._post("GICSIndustryGroup", {"sectorId": sector["id"]}):
                groups.append(
                    {
                        "sector_id": sector["id"],
                        "sector_name": sector["name"],
                        "industry_group_id": group["id"],
                        "industry_group": re.sub(r"^S&P/CSE\s+", "", group["name"]),
                    }
                )
        return groups

    def resolve_group(self, requested: str) -> dict:
        normalized = normalize_group_name(requested)
        normalized = CURRENT_NAME_ALIASES.get(normalized, normalized)
        match = next(
            (
                g
                for g in self.industry_groups()
                if normalize_group_name(g["industry_group"]) == normalized
            ),
            None,
        )
        if match is None:
            raise ValueError(
                f"Unknown CSE GICS industry group {requested!r}. Supported values: "
                + ", ".join(SUPPORTED_INDUSTRY_GROUPS)
            )
        return match

    def companies(self, requested: str) -> tuple[dict, list[dict]]:
        group = self.resolve_group(requested)
        response = self._post(
            "gics_sector_companies",
            {
                "sectorId": group["sector_id"],
                "industryGroupId": group["industry_group_id"],
            },
        )
        companies = []
        for row in response.get("reqIndustryBySectors", []):
            companies.append(
                {
                    "ticker": row["symbol"],
                    "name": row["name"],
                    "sector": group["industry_group"],
                    "gics_sector": group["sector_name"],
                    "industry_group": group["industry_group"],
                    "profile_url": "https://www.cse.lk/pages/company-profile/company-profile.component.html"
                    f"?symbol={row['symbol']}",
                    "classification_source_url": GICS_PAGE,
                    "documents": [],
                    "market_data": {
                        "price": row.get("price"),
                        "market_cap": row.get("marketCap"),
                        "share_volume": row.get("sharevolume"),
                        "trade_volume": row.get("tradevolume"),
                        "turnover": row.get("turnover"),
                        "last_traded_time": row.get("lastTradedTime"),
                        "market_source_url": f"{CSE_API}/gics_sector_companies",
                    },
                }
            )
        return group, companies


def apply_universe_config(
    group: dict, companies: list[dict], settings: dict | None, as_of: date
) -> tuple[list[dict], list[dict]]:
    """Apply explicit membership overlays and return selected issuers plus an audit table."""
    settings = settings or {}
    selected = {item["ticker"]: dict(item) for item in companies}
    decisions = {ticker: "included from CSE classification" for ticker in selected}
    membership = {ticker: "official_cse" for ticker in selected}

    overrides = settings.get("overrides") or {}
    for ticker, values in overrides.items():
        if ticker not in selected:
            raise ValueError(f"Universe override ticker {ticker!r} is not in the CSE response")
        selected[ticker].update(values or {})
        decisions[ticker] = "included from CSE classification with configured metadata override"

    for item in settings.get("include") or []:
        ticker = item["ticker"]
        requested_group = item.get("industry_group") or item.get("sector")
        if requested_group and normalize_group_name(requested_group) != normalize_group_name(
            group["industry_group"]
        ):
            continue
        if ticker in selected:
            selected[ticker].update({key: value for key, value in item.items() if key != "ticker"})
            decisions[ticker] = "explicitly included; also present in CSE classification"
            membership[ticker] = "configured_include+cse"
            continue
        selected[ticker] = {
            "ticker": ticker,
            "name": item.get("name") or ticker,
            "sector": group["industry_group"],
            "gics_sector": item.get("gics_sector") or group["sector_name"],
            "industry_group": group["industry_group"],
            "profile_url": item.get("profile_url")
            or "https://www.cse.lk/pages/company-profile/company-profile.component.html"
            f"?symbol={ticker}",
            "classification_source_url": item.get("classification_source_url")
            or "config/companies.yml",
            "documents": item.get("documents", []),
            "market_data": None,
        }
        decisions[ticker] = "explicitly included by configuration"
        membership[ticker] = "configured_include"

    all_tickers = set(selected)
    excluded = set(settings.get("exclude") or [])
    audit = []
    for ticker in sorted(all_tickers | excluded):
        issuer = selected.get(ticker)
        is_included = issuer is not None and ticker not in excluded
        audit.append(
            {
                "Ticker": ticker,
                "Company": issuer.get("name") if issuer else None,
                "GICS Sector": issuer.get("gics_sector") if issuer else group["sector_name"],
                "GICS Industry Group": issuer.get("industry_group")
                if issuer
                else group["industry_group"],
                "CSE Profile URL": issuer.get("profile_url") if issuer else None,
                "Classification As Of": as_of.isoformat(),
                "Classification Source URL": issuer.get("classification_source_url")
                if issuer
                else GICS_PAGE,
                "Membership Source": membership.get(ticker, "configured_exclusion_not_present"),
                "Included": is_included,
                "Decision": "excluded by configuration"
                if ticker in excluded
                else decisions[ticker],
            }
        )
    return [selected[ticker] for ticker in sorted(selected) if ticker not in excluded], audit
