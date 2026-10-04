from datetime import date

import pytest

from cse_screening.downloaders.universe import (
    CSEUniverseClient,
    apply_universe_config,
    normalize_group_name,
)


def test_group_name_normalization_handles_spacing_and_prefix():
    assert normalize_group_name(
        "S&P/CSE Real Estate Management&Development"
    ) == normalize_group_name("Real Estate Management & Development")


def test_company_universe_response_mapping(monkeypatch):
    client = CSEUniverseClient()
    monkeypatch.setattr(
        client,
        "industry_groups",
        lambda: [
            {
                "sector_id": 5,
                "sector_name": "Industrials",
                "industry_group_id": 7,
                "industry_group": "Capital Goods",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "_post",
        lambda endpoint, data=None: {
            "reqIndustryBySectors": [
                {
                    "symbol": "TEST.N0000",
                    "name": "TEST PLC",
                    "price": 10,
                    "marketCap": 1000,
                    "sharevolume": 50,
                }
            ]
        },
    )
    group, companies = client.companies("capital goods")
    assert group["industry_group_id"] == 7
    assert companies[0]["ticker"] == "TEST.N0000"
    assert companies[0]["market_data"]["price"] == 10


def test_legacy_real_estate_name_resolves_to_current_cse_name(monkeypatch):
    client = CSEUniverseClient()
    monkeypatch.setattr(
        client,
        "industry_groups",
        lambda: [
            {
                "sector_id": 11,
                "sector_name": "Real Estate",
                "industry_group_id": 19,
                "industry_group": "Real Estate",
            }
        ],
    )
    assert client.resolve_group("Real Estate Management&Development")["industry_group_id"] == 19


def test_config_can_include_exclude_and_override_independently():
    group = {"sector_name": "Industrials", "industry_group": "Capital Goods"}
    official = [
        {
            "ticker": "KEEP.N0000",
            "name": "KEEP PLC",
            "gics_sector": "Industrials",
            "industry_group": "Capital Goods",
            "profile_url": "https://www.cse.lk/keep",
            "classification_source_url": "https://www.cse.lk/gics",
            "documents": [],
            "market_data": {},
        },
        {
            "ticker": "DROP.N0000",
            "name": "DROP PLC",
            "gics_sector": "Industrials",
            "industry_group": "Capital Goods",
            "profile_url": "https://www.cse.lk/drop",
            "classification_source_url": "https://www.cse.lk/gics",
            "documents": [],
            "market_data": {},
        },
    ]
    selected, audit = apply_universe_config(
        group,
        official,
        {
            "exclude": ["DROP.N0000"],
            "include": [
                {
                    "ticker": "ADD.N0000",
                    "name": "ADDED PLC",
                    "industry_group": "Capital Goods",
                }
            ],
            "overrides": {"KEEP.N0000": {"name": "KEEP RENAMED PLC"}},
        },
        date(2026, 10, 4),
    )
    assert [item["ticker"] for item in selected] == ["ADD.N0000", "KEEP.N0000"]
    assert selected[1]["name"] == "KEEP RENAMED PLC"
    decisions = {item["Ticker"]: item for item in audit}
    assert decisions["DROP.N0000"]["Included"] is False
    assert decisions["ADD.N0000"]["Membership Source"] == "configured_include"
    assert decisions["KEEP.N0000"]["CSE Profile URL"] == "https://www.cse.lk/keep"
    assert decisions["KEEP.N0000"]["Classification As Of"] == "2026-10-04"


def test_unknown_metadata_override_is_not_silently_ignored():
    group = {"sector_name": "Industrials", "industry_group": "Capital Goods"}
    with pytest.raises(ValueError, match="not in the CSE response"):
        apply_universe_config(
            group,
            [],
            {"overrides": {"TYPO.N0000": {"name": "TYPO"}}},
            date(2026, 10, 4),
        )
