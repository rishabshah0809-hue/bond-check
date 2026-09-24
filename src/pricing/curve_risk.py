"""Curve-based pricing: price off a zero curve, key-rate durations, carry & roll-down.

Conventions:
- Cash-flow time t = year_fraction(settlement, date, bond.day_count) (30/360 default),
  consistent with the yield-based engine; discounting D(t) = exp(-z(t) t).
- Key-rate durations: zero-rate bumps shaped as triangles centred on each key tenor,
  zero at neighbouring keys, held flat (=1) before the first and after the last key.
  The bumps sum to a parallel shift, so sum(KRD) = effective (parallel) duration.
  KRD_i = -(P(+h) - P(-h)) / (2 h P), h = 1bp, P dirty. Measured against CONTINUOUS
  zero rates, so on a flat curve sum(KRD) = Macaulay duration.
- Carry & roll-down over a horizon (default 12 months), no funding cost (no repo),
  coupons received in the horizon are NOT reinvested:
    carry     = coupons + (dirty at horizon at today's YTM - dirty today)
    roll-down = dirty at horizon off the UNCHANGED curve - dirty at horizon at today's YTM
  "Unchanged curve" = same zero rates at the same tenors (static curve in tenor space).
  Today's YTM is the yield implied by the curve price.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from src.curves.curve import Curve
from src.pricing.daycount import year_fraction
from src.pricing.pricing import accrued_interest, dirty_price, ytm
from src.pricing.schedule import Bond, add_months, bond_cashflows

DEFAULT_KEY_TENORS: tuple[float, ...] = (1, 2, 5, 10, 15, 30)


def curve_dirty_price(bond: Bond, settlement_date: date, curve: Curve) -> float:
    """Dirty price per ``bond.face`` discounting each cash flow off ``curve``."""
    cf = bond_cashflows(bond, settlement_date)
    t = np.array([year_fraction(settlement_date, d, bond.day_count) for d in cf["date"]])
    return float(np.sum(cf["total"].to_numpy() * curve.discount(t)))


def curve_clean_price(bond: Bond, settlement_date: date, curve: Curve) -> float:
    """Clean price = curve dirty price - accrued interest."""
    return curve_dirty_price(bond, settlement_date, curve) - accrued_interest(
        bond, settlement_date
    )


def key_rate_bump(key_tenors: Sequence[float], i: int, size: float):
    """Triangular bump function for key tenor ``i`` (flat outside the end keys)."""
    k = np.asarray(key_tenors, dtype=float)
    y = np.zeros(len(k))
    y[i] = size

    def bump(t: np.ndarray) -> np.ndarray:
        return np.interp(t, k, y)  # np.interp is flat beyond the ends

    return bump


def key_rate_durations(
    bond: Bond,
    settlement_date: date,
    curve: Curve,
    key_tenors: Sequence[float] = DEFAULT_KEY_TENORS,
    bump_bps: float = 1.0,
) -> pd.Series:
    """Key-rate durations indexed by tenor (years); see module docstring."""
    h = bump_bps * 1e-4
    p0 = curve_dirty_price(bond, settlement_date, curve)
    out = {}
    for i, k in enumerate(key_tenors):
        up, dn = (
            curve_dirty_price(bond, settlement_date, curve.shifted(key_rate_bump(key_tenors, i, s)))
            for s in (h, -h)
        )
        out[k] = -(up - dn) / (2 * h * p0)
    return pd.Series(out, name="krd")


def carry_rolldown(
    bond: Bond,
    settlement_date: date,
    curve: Curve,
    horizon_months: int = 12,
) -> dict[str, float]:
    """Expected return over the horizon if the curve does not move (see module docstring).

    Returns currency amounts per ``bond.face`` and percentages of today's dirty price.
    Horizon at/after maturity is not supported (raises ValueError).
    """
    horizon = add_months(settlement_date, horizon_months)
    if horizon >= bond.maturity_date:
        raise ValueError("horizon must end before maturity")
    p0 = curve_dirty_price(bond, settlement_date, curve)
    y0 = ytm(p0 - accrued_interest(bond, settlement_date), bond, settlement_date)
    cf = bond_cashflows(bond, settlement_date)
    coupons = float(cf.loc[cf["date"] <= horizon, "total"].sum())
    p_h_const_yield = dirty_price(bond, horizon, y0)
    p_h_curve = curve_dirty_price(bond, horizon, curve)
    carry = coupons + p_h_const_yield - p0
    roll = p_h_curve - p_h_const_yield
    return {
        "horizon_date": horizon,
        "ytm": y0,
        "dirty_today": p0,
        "coupons": coupons,
        "carry": carry,
        "rolldown": roll,
        "total": carry + roll,
        "carry_pct": carry / p0 * 100,
        "rolldown_pct": roll / p0 * 100,
        "total_pct": (carry + roll) / p0 * 100,
    }
