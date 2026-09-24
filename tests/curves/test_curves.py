"""Tests for src.curves and curve-based pricing. All curves/bonds are ILLUSTRATIVE."""

from datetime import date

import numpy as np
import pytest

from src.curves import FlatCurve, InterpolatedCurve, NSSCurve, fit_nss
from src.pricing import Bond, dirty_price, macaulay_duration
from src.pricing.curve_risk import (
    DEFAULT_KEY_TENORS,
    carry_rolldown,
    curve_dirty_price,
    key_rate_durations,
)

SETTLE = date(2026, 3, 10)
TEN_Y = Bond(coupon_rate=0.0718, maturity_date=date(2036, 7, 15))
FORTY_Y = Bond(coupon_rate=0.0730, maturity_date=date(2066, 6, 19))
# ILLUSTRATIVE upward-sloping NSS curve
TRUE = NSSCurve(b0=0.072, b1=-0.015, b2=0.01, b3=-0.005, tau1=1.8, tau2=9.0)
TENORS = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40])


# ---------- NSS ----------
def test_nss_limits():
    assert TRUE.zero(1e-9) == pytest.approx(TRUE.b0 + TRUE.b1, abs=1e-8)
    assert TRUE.zero(1e6) == pytest.approx(TRUE.b0, abs=1e-5)


@pytest.mark.parametrize("rate_type", ["zero", "par"])
def test_fit_recovers_synthetic_curve(rate_type):
    obs = TRUE.zero(TENORS) if rate_type == "zero" else TRUE.par_yield(TENORS)
    fit = fit_nss(TENORS, obs, rate_type=rate_type)
    assert fit.rmse_bps < 0.01
    grid = np.linspace(0.25, 40, 50)
    assert np.max(np.abs(fit.curve.zero(grid) - TRUE.zero(grid))) < 1e-5


def test_fit_drops_missing_points_without_filling():
    obs = TRUE.zero(TENORS).copy()
    obs[3] = np.nan
    fit = fit_nss(TENORS, obs, rate_type="zero")
    assert fit.n_dropped == 1 and len(fit.tenors) == len(TENORS) - 1


def test_fit_needs_enough_points():
    with pytest.raises(ValueError, match="needs >= 6"):
        fit_nss([1, 2, 5], [0.07, 0.071, 0.072])
    assert fit_nss([1, 2, 5, 10], [0.065, 0.068, 0.07, 0.071], model="NS").rmse_bps < 1


def test_par_yield_of_flat_curve():
    r = 0.07
    expected = 2 * (np.exp(r / 2) - 1)  # continuous -> semi-annual
    assert FlatCurve(r).par_yield(10.0) == pytest.approx(expected, abs=1e-12)


def test_interpolated_curve_hits_pillars_and_is_flat_outside():
    c = InterpolatedCurve([1, 5, np.nan], [0.06, 0.07, 0.08])
    assert c.zero(1) == pytest.approx(0.06) and c.zero(5) == pytest.approx(0.07)
    assert c.zero(3) == pytest.approx(0.065)
    assert c.zero(0.1) == pytest.approx(0.06) and c.zero(30) == pytest.approx(0.07)


# ---------- curve pricing ----------
def test_flat_curve_price_matches_ytm_price():
    r = 0.07
    y = 2 * (np.exp(r / 2) - 1)
    assert curve_dirty_price(TEN_Y, SETTLE, FlatCurve(r)) == pytest.approx(
        dirty_price(TEN_Y, SETTLE, y), abs=1e-10
    )


@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y])
def test_krd_sum_equals_parallel_duration(bond):
    krd = key_rate_durations(bond, SETTLE, TRUE)
    h = 1e-4
    p0 = curve_dirty_price(bond, SETTLE, TRUE)
    up = curve_dirty_price(bond, SETTLE, TRUE.shifted(lambda t: np.full_like(t, h)))
    dn = curve_dirty_price(bond, SETTLE, TRUE.shifted(lambda t: np.full_like(t, -h)))
    assert krd.sum() == pytest.approx(-(up - dn) / (2 * h * p0), rel=1e-6)
    assert list(krd.index) == list(DEFAULT_KEY_TENORS)


def test_krd_on_flat_curve_sums_to_macaulay():
    r = 0.07
    y = 2 * (np.exp(r / 2) - 1)
    krd = key_rate_durations(TEN_Y, SETTLE, FlatCurve(r))
    assert krd.sum() == pytest.approx(macaulay_duration(TEN_Y, SETTLE, y), rel=1e-6)


def test_zero_coupon_at_key_tenor_loads_on_one_bucket():
    settle = date(2026, 1, 15)
    zero = Bond(coupon_rate=0.0, maturity_date=date(2036, 1, 15))  # exactly 10Y (30/360)
    krd = key_rate_durations(zero, settle, TRUE)
    assert krd[10] == pytest.approx(10.0, rel=1e-6)
    assert krd.drop(10).abs().max() < 1e-9


# ---------- carry & roll-down ----------
def test_flat_curve_has_no_rolldown_and_returns_about_yield():
    r = 0.07
    res = carry_rolldown(TEN_Y, SETTLE, FlatCurve(r))
    assert res["rolldown"] == pytest.approx(0, abs=1e-9)
    assert res["total_pct"] == pytest.approx(res["ytm"] * 100, abs=0.3)  # no reinvestment


def test_upward_curve_positive_rolldown():
    res = carry_rolldown(TEN_Y, SETTLE, TRUE)
    assert res["rolldown"] > 0
    assert res["total"] == pytest.approx(res["carry"] + res["rolldown"])


def test_horizon_past_maturity_raises():
    short = Bond(coupon_rate=0.065, maturity_date=date(2026, 7, 15))
    with pytest.raises(ValueError):
        carry_rolldown(short, SETTLE, TRUE)
