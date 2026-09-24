"""Nelson-Siegel and Nelson-Siegel-Svensson zero curves and fitting.

Model (zero rate, continuously compounded, t in years):
    z(t) = b0 + b1 * L(t/tau1) + b2 * (L(t/tau1) - e^(-t/tau1))
              + b3 * (L(t/tau2) - e^(-t/tau2)),          L(x) = (1 - e^-x) / x
Nelson-Siegel is the special case b3 = 0.
Interpretation: level = b0 (z(inf)), slope = b1 (z(0) - z(inf)), curvature = b2 (hump).

Fitting: least squares on yield errors (zero or par, per ``rate_type``), unweighted,
multi-start over a tau grid, with bounds. Missing (NaN) inputs are dropped, never filled.
Assumptions: inputs are decimals; par inputs are semi-annual par yields (see curve.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from src.curves.curve import Curve

_T_MIN = 1e-8


def _loading(t: np.ndarray, tau: float) -> tuple[np.ndarray, np.ndarray]:
    x = np.maximum(t, _T_MIN) / tau
    load = -np.expm1(-x) / x
    return load, load - np.exp(-x)


@dataclass(frozen=True)
class NSSCurve(Curve):
    """NSS zero curve. Set b3=0 for plain Nelson-Siegel (tau2 then unused)."""

    b0: float
    b1: float
    b2: float
    b3: float = 0.0
    tau1: float = 1.0
    tau2: float = 5.0

    def zero(self, t):
        t = np.asarray(t, dtype=float)
        l1, h1 = _loading(t, self.tau1)
        _, h2 = _loading(t, self.tau2)
        return self.b0 + self.b1 * l1 + self.b2 * h1 + self.b3 * h2

    @property
    def level(self) -> float:
        return self.b0

    @property
    def slope(self) -> float:
        return self.b1

    @property
    def curvature(self) -> float:
        return self.b2


@dataclass(frozen=True)
class NSSFit:
    """Fitted curve plus diagnostics (errors in decimal yield)."""

    curve: NSSCurve
    tenors: np.ndarray
    observed: np.ndarray
    fitted: np.ndarray
    rate_type: str
    model: str
    n_dropped: int = 0
    residuals: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", self.fitted - self.observed)

    @property
    def rmse_bps(self) -> float:
        return float(np.sqrt(np.mean(self.residuals**2)) * 1e4)


def _model_rates(curve: NSSCurve, tenors: np.ndarray, rate_type: str) -> np.ndarray:
    if rate_type == "zero":
        return curve.zero(tenors)
    return np.asarray(curve.par_yield(tenors), dtype=float)


def fit_nss(
    tenors,
    rates,
    rate_type: str = "par",
    model: str = "NSS",
) -> NSSFit:
    """Fit NS/NSS to observed yields.

    ``rate_type``: "par" (semi-annual par yields, e.g. a par curve) or "zero"
    (continuously compounded zero rates). ``model``: "NSS" (6 params, needs >= 6 points)
    or "NS" (4 params, needs >= 4). Raises ValueError on too few valid points.
    """
    if rate_type not in ("par", "zero"):
        raise ValueError("rate_type must be 'par' or 'zero'")
    if model not in ("NS", "NSS"):
        raise ValueError("model must be 'NS' or 'NSS'")
    t_all = np.asarray(tenors, dtype=float)
    r_all = np.asarray(rates, dtype=float)
    ok = np.isfinite(t_all) & np.isfinite(r_all) & (t_all > 0)
    t, r = t_all[ok], r_all[ok]
    need = 6 if model == "NSS" else 4
    if len(t) < need:
        raise ValueError(f"{model} needs >= {need} valid points, got {len(t)}")

    def build(p: np.ndarray) -> NSSCurve:
        if model == "NS":
            return NSSCurve(p[0], p[1], p[2], 0.0, p[3], 5.0)
        return NSSCurve(*p)

    def resid(p: np.ndarray) -> np.ndarray:
        return _model_rates(build(p), t, rate_type) - r

    long_r, short_r = r[np.argmax(t)], r[np.argmin(t)]
    if model == "NS":
        lb, ub = [-0.1, -0.5, -1.0, 0.05], [0.5, 0.5, 1.0, 30.0]
        starts = [[long_r, short_r - long_r, 0.0, tau] for tau in (0.5, 1.5, 3.0, 8.0)]
    else:
        lb = [-0.1, -0.5, -1.0, -1.0, 0.05, 0.05]
        ub = [0.5, 0.5, 1.0, 1.0, 30.0, 30.0]
        starts = [
            [long_r, short_r - long_r, 0.0, 0.0, t1, t2]
            for t1 in (0.5, 1.5, 3.0)
            for t2 in (5.0, 10.0, 20.0)
        ]
    best = None
    for x0 in starts:
        x0 = np.clip(x0, np.array(lb) + 1e-9, np.array(ub) - 1e-9)
        res = least_squares(resid, x0, bounds=(lb, ub), xtol=1e-14, ftol=1e-14, gtol=1e-14)
        if best is None or res.cost < best.cost:
            best = res
    curve = build(best.x)
    return NSSFit(
        curve=curve,
        tenors=t,
        observed=r,
        fitted=_model_rates(curve, t, rate_type),
        rate_type=rate_type,
        model=model,
        n_dropped=int((~ok).sum()),
    )
