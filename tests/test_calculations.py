from decimal import Decimal as D

from cse_screening.calculations.ratios import dividend_yield, free_cash_flow, growth, roe


def test_roe_uses_average_equity():
    assert roe(D(20), D(120), D(80)) == D("0.2")


def test_dividend_yield():
    assert dividend_yield(D("2.5"), D(50)) == D("0.05")


def test_negative_growth_is_preserved():
    assert growth(D(80), D(100)) == D("-0.2")


def test_free_cash_flow_treats_capex_as_outflow():
    assert free_cash_flow(D(100), D(-30)) == D(70)
