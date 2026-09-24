"""Carry and roll-down: expected return over a horizon if the curve does not move.

Definitions (horizon H, default 12 months; all amounts per ``bond.face``):
- "Unchanged curve" = same zero rate at the same TENOR (static curve), so at H the
  bond is repriced off the same curve at its shorter remaining maturity.
- coupon_income  = coupons paid in (settlement, H] + accrued(H) - accrued(today)
                   (accrual basis; coupons are NOT reinvested)
- pull_to_par    = clean(H) at today's YTM - clean(today)    (ageing at constant yield)
- rolldown       = clean(H) off the curve - clean(H) at today's YTM   (curve slope)
- price_change   = pull_to_par + rolldown = clean(H) off curve - clean(today)
- total          = coupon_income + price_change
                 = coupons + dirty(H) - dirty(today)
Percentages are of today's dirty price. Today's price comes from the curve; today's
YTM is the yield implied by that price. No funding (repo) cost, no taxes.

Bonds maturing on or before H: the horizon is truncated to maturity
(``matures_in_horizon`` = True). Coupon income = all remaining coupons - accrued today,
price change = redemption (face) - clean today (all pull-to-par), roll-down = 0.
The return then covers a period shorter than H; ``horizon_date`` says which.
"""

from __future__ import annotations

from datetime import date

from src.curves.curve import Curve
from src.pricing.curve_pricing import curve_clean_price, curve_dirty_price
from src.pricing.pricing import accrued_interest, clean_price, ytm
from src.pricing.schedule import Bond, add_months, bond_cashflows


def carry_rolldown(
    bond: Bond, settlement_date: date, curve: Curve, horizon_months: int = 12
) -> dict:
    """Carry/roll-down breakdown over ``horizon_months`` (see module docstring)."""
    target = add_months(settlement_date, horizon_months)
    matures = bond.maturity_date <= target
    horizon = bond.maturity_date if matures else target

    dirty0 = curve_dirty_price(bond, settlement_date, curve)
    clean0 = curve_clean_price(bond, settlement_date, curve)
    ai0 = accrued_interest(bond, settlement_date)
    y0 = ytm(clean0, bond, settlement_date)
    cf = bond_cashflows(bond, settlement_date)
    coupons = float(cf.loc[cf["date"] <= horizon, "coupon"].sum())

    if matures:
        ai_h = 0.0
        pull = bond.face - clean0
        roll = 0.0
    else:
        ai_h = accrued_interest(bond, horizon)
        clean_h_const = clean_price(bond, horizon, y0)
        clean_h_curve = curve_clean_price(bond, horizon, curve)
        pull = clean_h_const - clean0
        roll = clean_h_curve - clean_h_const

    coupon_income = coupons + ai_h - ai0
    price_change = pull + roll
    total = coupon_income + price_change

    def pct(x: float) -> float:
        return x / dirty0 * 100

    return {
        "horizon_date": horizon,
        "matures_in_horizon": matures,
        "ytm": y0,
        "dirty_today": dirty0,
        "clean_today": clean0,
        "coupons_received": coupons,
        "coupon_income": coupon_income,
        "pull_to_par": pull,
        "rolldown": roll,
        "price_change": price_change,
        "total": total,
        "coupon_income_pct": pct(coupon_income),
        "pull_to_par_pct": pct(pull),
        "rolldown_pct": pct(roll),
        "price_change_pct": pct(price_change),
        "total_pct": pct(total),
    }
