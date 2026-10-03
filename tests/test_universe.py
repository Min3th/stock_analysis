from cse_screening.downloaders.universe import CSEUniverseClient, normalize_group_name


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
