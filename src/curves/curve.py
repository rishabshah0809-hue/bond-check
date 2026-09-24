"""Zero-coupon yield curves.

Conventions:
- A curve maps time in years ``t`` to a zero rate z(t), CONTINUOUSLY compounded;
  discount factor D(t) = exp(-z(t) * t). ``zero_rate(t, "semiannual")`` converts to the
  semi-annual equivalent 2 * (exp(z/2) - 1). OPEN QUESTION: confirm the compounding
  FBIL uses for its published ZCYC; inputs in another basis must be converted first.
- Forward rate between t1 < t2 is the continuous simple-average forward
  (z2 t2 - z1 t1) / (t2 - t1).
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
    """Base class: subclasses implement ``zero(t)`` (continuous zero rate)."""

    def zero(self, t: ArrayLike) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def zero_rate(self, t: ArrayLike, compounding: str = "continuous") -> np.ndarray:
        """Zero rate at t: "continuous" (native) or "semiannual" equivalent."""
        z = self.zero(np.asarray(t, dtype=float))
        if compounding == "continuous":
            return z
        if compounding == "semiannual":
            return 2.0 * np.expm1(z / 2.0)
        raise ValueError("compounding must be 'continuous' or 'semiannual'")

    def discount(self, t: ArrayLike) -> np.ndarray:
        """Discount factor exp(-z(t) t); D(0) = 1."""
        t = np.asarray(t, dtype=float)
        return np.exp(-self.zero(t) * t)

    def discount_factor(self, t: ArrayLike) -> np.ndarray:
        """Alias of :meth:`discount`."""
        return self.discount(t)

    def forward_rate(self, t1: ArrayLike, t2: ArrayLike) -> np.ndarray:
        """Continuously-compounded forward rate from t1 to t2 (t2 > t1 >= 0)."""
        t1, t2 = np.asarray(t1, dtype=float), np.asarray(t2, dtype=float)
        if np.any(t2 <= t1):
            raise ValueError("forward_rate needs t2 > t1")
        return (self.zero(t2) * t2 - self.zero(t1) * t1) / (t2 - t1)

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

    @classmethod
    def from_semiannual(cls, y: float) -> FlatCurve:
        """Flat curve equal to a semi-annually compounded rate ``y``."""
        return cls(2.0 * np.log1p(y / 2.0))

    def zero(self, t: ArrayLike) -> np.ndarray:
        return np.full(np.shape(t), self.rate, dtype=float)
