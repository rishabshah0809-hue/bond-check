"""Curve pricing, z-spread, KRD, carry/roll-down tests. Bonds/curves are ILLUSTRATIVE."""

from datetime import date

import numpy as np
import pytest

from src.curves import FlatCurve, NSSCurve
from src.pricing import Bond, clean_price, dirty_price, macaulay_duration
from src.pricing.carry_rolldown import carry_rolldown
from src.pricing.curve_pricing import (
    ZSpreadError,
    curve_clean_price,
    curve_dirty_price,
    z_spread,
)
from src.pricing.key_rate import DEFAULT_KEY_TENORS, key_rate_durations, parallel_duration

SETTLE = date(2026, 3, 10)
TEN_Y = Bond(coupon_rate=0.0718, maturity_date=date(2036, 7, 15))
FORTY_Y = Bond(coupon_rate=0.0730, maturity_date=date(2066, 6, 19))
SHORT = Bond(coupon_rate=0.0650, maturity_date=date(2026, 7, 15))
UPWARD = NSSCurve(b0=0.072, b1=-0.015, b2=0.01, b3=-0.005, tau1=1.8, tau2=9.0)


# ---------- curve pricing ----------
@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y, SHORT])
def test_flat_curve_price_matches_yield_price(bond):
    y = 0.07
    c = FlatCurve.from_semiannual(y)
    assert curve_dirty_price(bond, SETTLE, c) == pytest.approx(
        dirty_price(bond, SETTLE, y), abs=1e-10
    )


@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y])
def test_par_bond_on_flat_curve_at_coupon_is_100(bond):
    settle = date(2026, 1, 15) if bond is TEN_Y else date(2025, 12, 19)  # coupon dates
    c = FlatCurve.from_semiannual(bond.coupon_rate)
    assert curve_clean_price(bond, settle, c) == pytest.approx(100, abs=1e-9)
    # mid-period: within 5 paise (street convention, see Phase 1)
    assert curve_clean_price(bond, SETTLE, c) == pytest.approx(100, abs=0.05)


def test_z_spread_round_trip_and_sign():
    target = curve_clean_price(TEN_Y, SETTLE, UPWARD, 0.0035)
    assert z_spread(target, TEN_Y, SETTLE, UPWARD) == pytest.approx(0.0035, abs=1e-10)
    assert z_spread(curve_clean_price(TEN_Y, SETTLE, UPWARD), TEN_Y, SETTLE, UPWARD) == \
        pytest.approx(0, abs=1e-10)


def test_z_spread_on_flat_curve_equals_yield_gap():
    c = FlatCurve.from_semiannual(0.07)
    px = clean_price(TEN_Y, SETTLE, 0.075)
    s = z_spread(px, TEN_Y, SETTLE, c)
    assert s == pytest.approx(2 * np.log1p(0.075 / 2) - c.rate, abs=1e-10)


def test_z_spread_unreachable_price():
    with pytest.raises(ZSpreadError):
        z_spread(1.0, TEN_Y, SETTLE, UPWARD)


# ---------- KRD ----------
@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y, SHORT])
def test_krd_sum_equals_parallel_duration(bond):
    krd = key_rate_durations(bond, SETTLE, UPWARD)
    assert list(krd.index) == list(DEFAULT_KEY_TENORS)
    # tolerance: second-order bump interaction, ~1e-7 relative for 1bp
    assert krd.sum() == pytest.approx(parallel_duration(bond, SETTLE, UPWARD), rel=1e-6)


def test_krd_flat_curve_sums_to_macaulay():
    y = 0.07
    krd = key_rate_durations(TEN_Y, SETTLE, FlatCurve.from_semiannual(y))
    assert krd.sum() == pytest.approx(macaulay_duration(TEN_Y, SETTLE, y), rel=1e-6)


def test_zero_coupon_krd_in_maturity_bucket():
    settle = date(2026, 1, 15)
    at_key = Bond(coupon_rate=0.0, maturity_date=date(2036, 1, 15))  # exactly 10Y
    krd = key_rate_durations(at_key, settle, UPWARD)
    assert krd[10] == pytest.approx(10.0, rel=1e-6)
    assert krd.drop(10).abs().max() < 1e-9
    # 12Y zero: split between the neighbouring 10Y and 15Y buckets only
    between = Bond(coupon_rate=0.0, maturity_date=date(2038, 1, 15))
    k2 = key_rate_durations(between, settle, UPWARD)
    assert k2[10] == pytest.approx(12 * 0.6, rel=1e-5)
    assert k2[15] == pytest.approx(12 * 0.4, rel=1e-5)
    assert k2.drop([10, 15]).abs().max() < 1e-9


# ---------- carry & roll-down ----------
def test_flat_curve_no_rolldown_carry_about_yield():
    y = 0.07
    r = carry_rolldown(TEN_Y, SETTLE, FlatCurve.from_semiannual(y))
    assert not r["matures_in_horizon"]
    assert r["rolldown"] == pytest.approx(0, abs=1e-9)
    # coupons not reinvested and return measured on dirty price -> within 20bp of yield
    assert r["total_pct"] == pytest.approx(y * 100, abs=0.2)


def test_breakdown_adds_up_and_upward_curve_rolls_down_positively():
    r = carry_rolldown(TEN_Y, SETTLE, UPWARD)
    assert r["rolldown"] > 0
    assert r["total"] == pytest.approx(r["coupon_income"] + r["pull_to_par"] + r["rolldown"])
    horizon_dirty = curve_dirty_price(TEN_Y, r["horizon_date"], UPWARD)
    assert r["total"] == pytest.approx(r["coupons_received"] + horizon_dirty - r["dirty_today"])


def test_bond_maturing_within_horizon():
    r = carry_rolldown(SHORT, SETTLE, UPWARD)
    assert r["matures_in_horizon"] and r["horizon_date"] == SHORT.maturity_date
    assert r["rolldown"] == 0.0
    assert r["pull_to_par"] == pytest.approx(100 - r["clean_today"])
    # held to maturity: total = remaining cash (coupon + face) - dirty today
    assert r["total"] == pytest.approx(3.25 + 100 - r["dirty_today"])
