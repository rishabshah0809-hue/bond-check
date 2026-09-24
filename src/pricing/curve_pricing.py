"""Price bonds off a zero curve, and solve the z-spread that matches a market price.

Conventions:
- Cash flows from Phase 1 (``bond_cashflows``); time t = year_fraction(settlement,
  cash-flow date, bond.day_count) (30/360 default), consistent with the yield engine.
- Discount factor D(t) = exp(-(z(t) + s) t): z continuous zero rate from the curve,
  s the z-spread (continuous, constant across maturities; 0 for pure curve price).
- Clean = dirty - accrued (Phase 1 accrued interest). Prices per ``bond.face``.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from scipy.optimize import brentq

from src.curves.curve import Curve
from src.pricing.daycount import year_fraction
from src.pricing.pricing import accrued_interest
from src.pricing.schedule import Bond, bond_cashflows


class ZSpreadError(RuntimeError):
    """Raised when no z-spread in the search range reproduces the price."""


def _times_and_cfs(bond: Bond, settlement_date: date) -> tuple[np.ndarray, np.ndarray]:
    cf = bond_cashflows(bond, settlement_date)
    t = np.array([year_fraction(settlement_date, d, bond.day_count) for d in cf["date"]])
    return t, cf["total"].to_numpy(dtype=float)


def curve_dirty_price(
    bond: Bond, settlement_date: date, curve: Curve, z_spread: float = 0.0
) -> float:
    """Dirty price per ``bond.face``: sum CF * exp(-(z(t) + z_spread) t)."""
    t, cf = _times_and_cfs(bond, settlement_date)
    return float(np.sum(cf * curve.discount(t) * np.exp(-z_spread * t)))


def curve_clean_price(
    bond: Bond, settlement_date: date, curve: Curve, z_spread: float = 0.0
) -> float:
    """Clean price = curve dirty price - accrued interest."""
    return curve_dirty_price(bond, settlement_date, curve, z_spread) - accrued_interest(
        bond, settlement_date
    )


def z_spread(
    clean_price: float,
    bond: Bond,
    settlement_date: date,
    curve: Curve,
    lower: float = -0.2,
    upper: float = 0.5,
) -> float:
    """Constant continuous spread over the zero curve matching ``clean_price`` (decimal).

    Positive = bond cheap to the curve. Solved with brentq on [lower, upper].
    """
    if not np.isfinite(clean_price) or clean_price <= 0:
        raise ValueError("clean_price must be a positive finite number")

    def f(s: float) -> float:
        return curve_clean_price(bond, settlement_date, curve, s) - clean_price

    if f(lower) * f(upper) > 0:
        raise ZSpreadError(
            f"No z-spread in [{lower * 1e4:.0f}, {upper * 1e4:.0f}] bp matches clean price "
            f"{clean_price:.4f} (range {f(upper) + clean_price:.4f}-{f(lower) + clean_price:.4f})."
        )
    return float(brentq(f, lower, upper, xtol=1e-12))
