"""Zero-coupon yield curves.

Conventions:
- A curve maps time in years ``t`` to a zero rate z(t), CONTINUOUSLY compounded;
  discount factor D(t) = exp(-z(t) * t). OPEN QUESTION: confirm the compounding FBIL
  uses for its published zero curve; inputs in another basis must be converted first.
- Time in years is measured by the caller (bond pricing uses the bond's day count,
  30/360 by default, so t = year_fraction(settlement, cash-flow date)).
- Par yields are semi-annual coupon rates on a schedule rolled back from T in 0.5y
  steps; a short first period accrues its fraction (so T < 0.5 is a single payment
  with simple accrual).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

ArrayLike = float | np.ndarray


class Curve:
    """Base class: subclasses implement ``zero(t)``."""

    def zero(self, t: ArrayLike) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def discount(self, t: ArrayLike) -> np.ndarray:
        """Discount factor exp(-z(t) t); D(0) = 1."""
        t = np.asarray(t, dtype=float)
        return np.exp(-self.zero(t) * t)

    def par_yield(self, maturity: ArrayLike, freq: int = 2) -> np.ndarray:
        """Par coupon rate (compounded ``freq``/yr) for maturity(ies) in years."""
        mats = np.atleast_1d(np.asarray(maturity, dtype=float))
        out = np.empty_like(mats)
        step = 1.0 / freq
        for i, m in enumerate(mats):
            n = int(np.ceil(m / step - 1e-9))
            times = m - step * np.arange(n)[::-1]
            accr = np.diff(np.concatenate([[0.0], times]))  # first period may be a stub
            df = self.discount(times)
            out[i] = (1.0 - df[-1]) / np.sum(accr * df)
        return out if np.ndim(maturity) else out[0]

    def shifted(self, bump: Callable[[np.ndarray], np.ndarray]) -> Curve:
        """New curve with zero(t) + bump(t) (bump in decimal, e.g. 1bp = 1e-4)."""
        return ShiftedCurve(self, bump)


@dataclass(frozen=True)
class ShiftedCurve(Curve):
    """Base curve plus an additive zero-rate bump function."""

    base: Curve
    bump: Callable[[np.ndarray], np.ndarray]

    def zero(self, t: ArrayLike) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        return self.base.zero(t) + self.bump(t)


@dataclass(frozen=True)
class FlatCurve(Curve):
    """Constant continuously-compounded zero rate."""

    rate: float

    def zero(self, t: ArrayLike) -> np.ndarray:
        return np.full(np.shape(t), self.rate, dtype=float)


class InterpolatedCurve(Curve):
    """Linear interpolation of zero rates between pillars; flat beyond the ends.

    Assumes pillars are zero rates (continuous). NaN pillars are dropped, never filled.
    """

    def __init__(self, tenors: np.ndarray, zeros: np.ndarray):
        t = np.asarray(tenors, dtype=float)
        z = np.asarray(zeros, dtype=float)
        ok = np.isfinite(t) & np.isfinite(z)
        if ok.sum() < 1:
            raise ValueError("need at least one non-missing pillar")
        order = np.argsort(t[ok])
        self.tenors, self.zeros = t[ok][order], z[ok][order]

    def zero(self, t: ArrayLike) -> np.ndarray:
        return np.interp(np.asarray(t, dtype=float), self.tenors, self.zeros)
