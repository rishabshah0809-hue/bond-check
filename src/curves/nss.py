"""Nelson-Siegel(-Svensson) zero curves and fitting.

Model (zero rate, CONTINUOUSLY compounded, t in years):
    z(t) = b0 + b1 L(t/tau1) + b2 (L(t/tau1) - e^(-t/tau1)) + b3 (L(t/tau2) - e^(-t/tau2))
    L(x) = (1 - e^-x) / x
NS is the special case b3 = 0. level = b0 (= z(inf)), slope = b1 (= z(0) - z(inf)),
curvature = b2 (medium-term hump).

Inputs: a table of (tenor_years, yield) in DECIMAL, stated as either
- "par":  semi-annual par yields (e.g. a par curve). No separate bootstrap step is run:
          the NSS zero curve is fitted so that the par yields it implies (semi-annual
          coupons, see Curve.par_yield) match the inputs. This is equivalent to a smooth
          bootstrap and avoids the noise of point-by-point stripping.
- "zero": continuously-compounded zero rates, fitted directly.

Fitting: scipy least_squares on yield errors (unweighted), box bounds, multi-start
(fixed tau grid + seeded random starts, so results are deterministic). tau1 != tau2 is
enforced by the parametrisation tau2 = tau1 + d with d >= MIN_TAU_GAP.

Fallback to 4-parameter NS when: fewer than 6 valid points; or the NSS fit did not
converge; or it is "unstable" = a beta sits on its bound, or the Jacobian condition
number exceeds COND_MAX (near-collinear factors, which make parameters meaningless).

Input checks: < 4 valid points, non-positive tenors or duplicate tenors -> ValueError.
Unsorted tenors are sorted and flagged; NaN rows are dropped (never filled) and flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from src.curves.curve import Curve

_T_MIN = 1e-8
MIN_TAU_GAP = 0.25
COND_MAX = 1e8
DEFAULT_SEED = 20260925


def _loading(t: np.ndarray, tau: float) -> tuple[np.ndarray, np.ndarray]:
    x = np.maximum(t, _T_MIN) / tau
    load = -np.expm1(-x) / x
    return load, load - np.exp(-x)


@dataclass(frozen=True)
class NSSCurve(Curve):
    """NSS zero curve. b3=0 gives plain Nelson-Siegel (tau2 then unused)."""

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

    @property
    def params(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in ("b0", "b1", "b2", "b3", "tau1", "tau2")}


@dataclass(frozen=True)
class NSSFit:
    """Fitted curve plus diagnostics. Errors in decimal yield; *_bps in basis points."""

    curve: NSSCurve
    tenors: np.ndarray
    observed: np.ndarray
    fitted: np.ndarray
    rate_type: str
    method: str  # "NSS" or "NS"
    converged: bool
    n_dropped: int = 0
    warnings: tuple[str, ...] = ()
    curve_date: object = None
    residuals: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", self.fitted - self.observed)

    @property
    def model(self) -> str:
        return self.method

    @property
    def rmse_bps(self) -> float:
        return float(np.sqrt(np.mean(self.residuals**2)) * 1e4)

    @property
    def max_abs_error_bps(self) -> float:
        return float(np.max(np.abs(self.residuals)) * 1e4)

    @property
    def params(self) -> dict[str, float]:
        return self.curve.params

    def error_table(self):
        """DataFrame of tenor, observed, fitted, error (all in %, error in bp)."""
        import pandas as pd

        return pd.DataFrame(
            {
                "tenor_years": self.tenors,
                "observed_pct": self.observed * 100,
                "fitted_pct": self.fitted * 100,
                "error_bp": self.residuals * 1e4,
            }
        )


def _model_rates(curve: NSSCurve, tenors: np.ndarray, rate_type: str) -> np.ndarray:
    if rate_type == "zero":
        return curve.zero(tenors)
    return np.asarray(curve.par_yield(tenors), dtype=float)


def _clean_inputs(tenors, rates) -> tuple[np.ndarray, np.ndarray, int, list[str]]:
    t_all = np.asarray(tenors, dtype=float)
    r_all = np.asarray(rates, dtype=float)
    if t_all.shape != r_all.shape:
        raise ValueError("tenors and rates must have the same length")
    warns: list[str] = []
    ok = np.isfinite(t_all) & np.isfinite(r_all)
    n_dropped = int((~ok).sum())
    if n_dropped:
        warns.append(f"{n_dropped} missing point(s) dropped (not filled)")
    t, r = t_all[ok], r_all[ok]
    if np.any(t <= 0):
        raise ValueError("tenors must be > 0")
    uniq, counts = np.unique(t, return_counts=True)
    if np.any(counts > 1):
        raise ValueError(f"duplicate tenors: {uniq[counts > 1].tolist()}")
    if np.any(np.diff(t) <= 0):
        warns.append("tenors were not in increasing order; sorted")
        order = np.argsort(t)
        t, r = t[order], r[order]
    if len(t) < 4:
        raise ValueError(f"need >= 4 valid points to fit a curve, got {len(t)}")
    return t, r, n_dropped, warns


def _fit(t, r, rate_type, method, seed):
    long_r, short_r = r[-1], r[0]
    rng = np.random.default_rng(seed)
    if method == "NS":
        lb, ub = [-0.1, -0.5, -1.0, 0.05], [0.5, 0.5, 1.0, 30.0]

        def build(p):
            return NSSCurve(p[0], p[1], p[2], 0.0, p[3], p[3] + 5.0)

        grid = [[long_r, short_r - long_r, 0.0, tau] for tau in (0.5, 1.5, 3.0, 8.0)]
        rand = [[long_r, short_r - long_r, rng.uniform(-0.03, 0.03), rng.uniform(0.2, 10)]
                for _ in range(4)]
    else:
        lb = [-0.1, -0.5, -1.0, -1.0, 0.05, MIN_TAU_GAP]
        ub = [0.5, 0.5, 1.0, 1.0, 15.0, 30.0]

        def build(p):
            return NSSCurve(p[0], p[1], p[2], p[3], p[4], p[4] + p[5])

        grid = [[long_r, short_r - long_r, 0.0, 0.0, t1, t2 - t1]
                for t1 in (0.5, 1.5, 3.0) for t2 in (5.0, 10.0, 20.0)]
        rand = [[long_r, short_r - long_r, rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03),
                 rng.uniform(0.2, 5), rng.uniform(1, 20)] for _ in range(6)]

    def resid(p):
        return _model_rates(build(p), t, rate_type) - r

    lb_a, ub_a = np.array(lb), np.array(ub)
    best = None
    for x0 in grid + rand:
        x0 = np.clip(x0, lb_a + 1e-9, ub_a - 1e-9)
        res = least_squares(resid, x0, bounds=(lb_a, ub_a), xtol=1e-14, ftol=1e-14, gtol=1e-14)
        if best is None or res.cost < best.cost:
            best = res
    return build(best.x), best, lb_a, ub_a


def _nss_unstable(res, lb, ub) -> str | None:
    if not res.success:
        return "NSS did not converge"
    betas = res.x[:4]
    if np.any(np.isclose(betas, lb[:4], atol=1e-6)) or np.any(np.isclose(betas, ub[:4], atol=1e-6)):
        return "NSS beta at bound"
    s = np.linalg.svd(res.jac, compute_uv=False)
    if s[-1] == 0 or s[0] / s[-1] > COND_MAX:
        return "NSS parameters ill-conditioned"
    return None


def fit_nss(
    tenors,
    rates,
    rate_type: str = "par",
    model: str = "NSS",
    seed: int = DEFAULT_SEED,
    curve_date=None,
) -> NSSFit:
    """Fit NSS (default) or NS to yields in DECIMAL. See module docstring for rules."""
    if rate_type not in ("par", "zero"):
        raise ValueError("rate_type must be 'par' or 'zero'")
    if model not in ("NS", "NSS"):
        raise ValueError("model must be 'NS' or 'NSS'")
    t, r, n_dropped, warns = _clean_inputs(tenors, rates)

    method = model
    if model == "NSS" and len(t) < 6:
        warns.append(f"only {len(t)} points: fell back to 4-parameter NS")
        method = "NS"
    curve, res, lb, ub = _fit(t, r, rate_type, method, seed)
    if method == "NSS":
        why = _nss_unstable(res, lb, ub)
        if why:
            warns.append(f"{why}: fell back to 4-parameter NS")
            method = "NS"
            curve, res, lb, ub = _fit(t, r, rate_type, method, seed)
    return NSSFit(
        curve=curve,
        tenors=t,
        observed=r,
        fitted=_model_rates(curve, t, rate_type),
        rate_type=rate_type,
        method=method,
        converged=bool(res.success),
        n_dropped=n_dropped,
        warnings=tuple(warns),
        curve_date=curve_date,
    )
