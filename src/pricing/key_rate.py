"""Key-rate durations (KRD) on a zero curve.

Method:
- Key tenors default to 1, 2, 5, 10, 15, 30 years.
- For key i, the zero curve is bumped by a triangular profile: +h at key i, falling
  linearly to 0 at keys i-1 and i+1; the first key's bump is held flat (= h) for all
  shorter maturities and the last key's for all longer ones. The profiles sum to a
  parallel shift at every t.
- Full repricing (``curve_dirty_price``) at +h and -h, h = 1bp:
      KRD_i = -(P(+h) - P(-h)) / (2 h P0),  P = dirty price.
- Bumps apply to CONTINUOUS zero rates, so KRDs are durations w.r.t. continuous zero
  rates (on a flat curve their sum equals Macaulay duration, not modified duration).
- sum(KRD) equals the parallel-shift effective duration up to second-order terms:
  relative difference ~1e-7 for 1bp bumps (tests use rel. tolerance 1e-6).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from src.curves.curve import Curve
from src.pricing.curve_pricing import curve_dirty_price
from src.pricing.schedule import Bond

DEFAULT_KEY_TENORS: tuple[float, ...] = (1, 2, 5, 10, 15, 30)


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
    """KRDs indexed by key tenor (years). See module docstring for the method."""
    if list(key_tenors) != sorted(set(key_tenors)):
        raise ValueError("key_tenors must be strictly increasing")
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


def parallel_duration(
    bond: Bond, settlement_date: date, curve: Curve, bump_bps: float = 1.0
) -> float:
    """Effective duration for a parallel zero-curve shift (same bump size as KRD)."""
    h = bump_bps * 1e-4
    p0 = curve_dirty_price(bond, settlement_date, curve)
    up, dn = (
        curve_dirty_price(bond, settlement_date, curve.shifted(lambda t, s=s: np.full_like(t, s)))
        for s in (h, -h)
    )
    return -(up - dn) / (2 * h * p0)
