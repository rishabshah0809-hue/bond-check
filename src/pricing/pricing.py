"""Price, accrued interest and yield for fixed-coupon bonds.

Conventions (Indian G-sec defaults):
- Yield is a nominal annual rate compounded ``freq`` times a year.
- "Street" discounting with a fractional first period:
      dirty = sum_k CF_k / (1 + y/f) ** (w + k),   k = 0..n-1
  w = day_count(settlement, next_cpn) / day_count(prev_cpn, next_cpn).
  Compounded discounting is used even in the final period (no switch to simple
  interest when < 1 period remains). OPEN QUESTION: confirm vs FBIL/CCIL practice.
- Accrued = coupon_per_period * day_count(prev_cpn, settlement) / day_count(prev, next).
- Clean = dirty - accrued. Prices are per ``bond.face`` (per 100 by default).
"""

from __future__ import annotations

from datetime import date

import numpy as np
from scipy.optimize import brentq

from src.pricing.daycount import day_count
from src.pricing.schedule import Bond, bond_cashflows, coupon_dates


class YieldConvergenceError(RuntimeError):
    """Raised when the YTM solver cannot bracket or converge on a root."""


def _period_fraction(bond: Bond, settlement_date: date) -> tuple[float, date, date]:
    """Return (w, prev_cpn, next_cpn); w = fraction of the current period remaining."""
    prev, future = coupon_dates(bond, settlement_date)
    nxt = future[0]
    w = day_count(settlement_date, nxt, bond.day_count) / day_count(prev, nxt, bond.day_count)
    return w, prev, nxt


def discount_times(bond: Bond, settlement_date: date) -> tuple[np.ndarray, np.ndarray]:
    """Return (times in coupon periods, cash-flow amounts) for all future cash flows."""
    w, _, _ = _period_fraction(bond, settlement_date)
    cfs = bond_cashflows(bond, settlement_date)["total"].to_numpy(dtype=float)
    return w + np.arange(len(cfs), dtype=float), cfs


def accrued_interest(bond: Bond, settlement_date: date) -> float:
    """Accrued interest per ``bond.face`` on the bond's day count.

    Zero on a coupon date. Ex-interest (shut period) conventions are ignored.
    """
    w, _, _ = _period_fraction(bond, settlement_date)
    return bond.face * bond.coupon_rate / bond.freq * (1.0 - w)


def dirty_price(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Full (dirty) price per ``bond.face`` for yield ``ytm`` (decimal, compounded freq/yr)."""
    if ytm <= -bond.freq:
        raise ValueError("ytm must exceed -freq (discount factor undefined)")
    t, cf = discount_times(bond, settlement_date)
    return float(np.sum(cf / (1.0 + ytm / bond.freq) ** t))


def clean_price(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Clean price = dirty price - accrued interest, per ``bond.face``."""
    return dirty_price(bond, settlement_date, ytm) - accrued_interest(bond, settlement_date)


def ytm(
    clean_price: float,
    bond: Bond,
    settlement_date: date,
    lower: float = -0.5,
    upper: float = 2.0,
) -> float:
    """Yield to maturity (decimal) such that clean_price(y) == ``clean_price``.

    Solved with scipy brentq on [lower, upper]. Same conventions as dirty_price.
    Raises YieldConvergenceError if the price cannot be bracketed or brentq fails.
    """
    if not np.isfinite(clean_price) or clean_price <= 0:
        raise ValueError("clean_price must be a positive finite number")
    ai = accrued_interest(bond, settlement_date)
    target = clean_price + ai

    def f(y: float) -> float:
        return dirty_price(bond, settlement_date, y) - target

    f_lo, f_hi = f(lower), f(upper)
    if f_lo * f_hi > 0:
        raise YieldConvergenceError(
            f"Cannot solve YTM for clean price {clean_price:.4f}: attainable clean prices "
            f"for yields in [{lower:.0%}, {upper:.0%}] are "
            f"{f_hi + target - ai:.4f} to {f_lo + target - ai:.4f}."
        )
    root, res = brentq(f, lower, upper, xtol=1e-12, maxiter=200, full_output=True, disp=False)
    if not res.converged:
        raise YieldConvergenceError(f"brentq did not converge: {res.flag}")
    return float(root)
