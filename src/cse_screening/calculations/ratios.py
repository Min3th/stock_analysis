"""Null-safe financial calculations; negative inputs are preserved."""

from decimal import Decimal


def divide(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in {None, Decimal(0)}:
        return None
    return numerator / denominator


def growth(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous in {None, Decimal(0)}:
        return None
    return (current - previous) / abs(previous)


def cagr(end: Decimal | None, start: Decimal | None, years: int) -> Decimal | None:
    if end is None or start is None or years <= 0 or end < 0 or start <= 0:
        return None
    return (end / start) ** (Decimal(1) / Decimal(years)) - Decimal(1)


def roe(
    net_profit_attributable: Decimal | None,
    equity_current: Decimal | None,
    equity_previous: Decimal | None,
) -> Decimal | None:
    if equity_current is None or equity_previous is None:
        return None
    average = (equity_current + equity_previous) / Decimal(2)
    return divide(net_profit_attributable, average)


def roa(
    net_profit: Decimal | None, assets_current: Decimal | None, assets_previous: Decimal | None
) -> Decimal | None:
    if assets_current is None or assets_previous is None:
        return None
    return divide(net_profit, (assets_current + assets_previous) / Decimal(2))


def debt_to_equity(debt: Decimal | None, equity: Decimal | None) -> Decimal | None:
    return divide(debt, equity)


def net_debt(debt: Decimal | None, cash: Decimal | None) -> Decimal | None:
    return None if debt is None or cash is None else debt - cash


def free_cash_flow(operating_cash_flow: Decimal | None, capex: Decimal | None) -> Decimal | None:
    return (
        None if operating_cash_flow is None or capex is None else operating_cash_flow - abs(capex)
    )


def price_earnings(price: Decimal | None, eps: Decimal | None) -> Decimal | None:
    return divide(price, eps)


def price_to_book(price: Decimal | None, bvps: Decimal | None) -> Decimal | None:
    return divide(price, bvps)


def dividend_yield(dps: Decimal | None, price: Decimal | None) -> Decimal | None:
    return divide(dps, price)


def payout_ratio(dps: Decimal | None, eps: Decimal | None) -> Decimal | None:
    return divide(dps, eps)
