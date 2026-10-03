"""Discover a current industry-group universe from the official CSE GICS APIs."""

from __future__ import annotations

import re
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
