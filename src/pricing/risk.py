"""Duration, convexity, DV01 and the yield-shock comparison table.

Conventions: as pricing.py (compounded at ``freq``, fractional first period).
- Macaulay duration (years) = sum(t_k/f * PV_k) / dirty, t_k in coupon periods, so
  years are on the bond's day-count basis (30/360 by default).
- Modified duration = Macaulay / (1 + y/f)  ( = -(1/P) dP/dy ).
- Convexity (years^2) = (1/P) d2P/dy2 = sum(CF_k t_k (t_k+1) / (1+y/f)^(t_k+2)) / (f^2 P).
- DV01 = modified duration * dirty * 1e-4 per ``bond.face``; positive = loss for +1bp.
- Shock table works on dirty price with accrued held constant, so clean and dirty
  changes in currency are identical. Shocks are parallel shifts of the bond's own YTM.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from src.pricing.pricing import dirty_price, discount_times
from src.pricing.schedule import Bond

DEFAULT_SHOCKS_BPS: tuple[int, ...] = tuple(range(-100, 101, 25))


def _pv(bond: Bond, settlement_date: date, ytm: float):
    t, cf = discount_times(bond, settlement_date)
    base = 1.0 + ytm / bond.freq
    pv = cf / base**t
    return t, cf, base, pv, float(pv.sum())


def macaulay_duration(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Macaulay duration in years: PV-weighted average time to cash flows."""
    t, _, _, pv, p = _pv(bond, settlement_date, ytm)
    return float(np.sum(t * pv) / p / bond.freq)


def modified_duration(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Modified duration = Macaulay / (1 + y/freq)."""
    return macaulay_duration(bond, settlement_date, ytm) / (1.0 + ytm / bond.freq)


def convexity(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Analytic convexity (1/P) d2P/dy2 in years^2 (y compounded ``freq``/yr)."""
    t, cf, base, _, p = _pv(bond, settlement_date, ytm)
    return float(np.sum(cf * t * (t + 1) / base ** (t + 2)) / (bond.freq**2 * p))


def dv01(bond: Bond, settlement_date: date, ytm: float) -> float:
    """Dollar value of 1bp per ``bond.face`` (analytic: modified duration * dirty * 1e-4)."""
    p = dirty_price(bond, settlement_date, ytm)
    return modified_duration(bond, settlement_date, ytm) * p * 1e-4


def yield_shock_table(
    bond: Bond,
    settlement_date: date,
    ytm: float,
    shocks_bps: Sequence[float] = DEFAULT_SHOCKS_BPS,
) -> pd.DataFrame:
    """Price change under parallel yield shocks by three methods, side by side.

    Columns: shock_bps, yield, full_price (repriced dirty), and % price change by
    full revaluation, duration only (-D dy) and duration+convexity
    (-D dy + C dy^2 / 2), plus each approximation's error vs full (percentage points).
    """
    p0 = dirty_price(bond, settlement_date, ytm)
    d = modified_duration(bond, settlement_date, ytm)
    c = convexity(bond, settlement_date, ytm)
    rows = []
    for s in shocks_bps:
        dy = s / 1e4
        p1 = dirty_price(bond, settlement_date, ytm + dy)
        full = (p1 / p0 - 1) * 100
        dur = -d * dy * 100
        dc = (-d * dy + 0.5 * c * dy**2) * 100
        rows.append(
            {
                "shock_bps": s,
                "yield": ytm + dy,
                "full_price": p1,
                "full_reval_pct": full,
                "duration_pct": dur,
                "dur_convexity_pct": dc,
                "duration_err_pct": dur - full,
                "dur_convexity_err_pct": dc - full,
            }
        )
    return pd.DataFrame(rows)
