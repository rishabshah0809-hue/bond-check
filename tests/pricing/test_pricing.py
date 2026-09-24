"""Tests for src.pricing. All bonds and yields here are ILLUSTRATIVE, not market data."""

from datetime import date

import numpy as np
import pytest

from src.pricing import (
    Bond,
    YieldConvergenceError,
    accrued_interest,
    clean_price,
    convexity,
    day_count,
    dirty_price,
    dv01,
    generate_cashflows,
    macaulay_duration,
    modified_duration,
    year_fraction,
    yield_shock_table,
    ytm,
)

# ILLUSTRATIVE sample bonds
SETTLE = date(2026, 3, 10)
TEN_Y = Bond(coupon_rate=0.0718, maturity_date=date(2036, 7, 15))
FORTY_Y = Bond(coupon_rate=0.0730, maturity_date=date(2066, 6, 19))
SHORT = Bond(coupon_rate=0.0650, maturity_date=date(2026, 7, 15))  # < 6 months
ZERO = Bond(coupon_rate=0.0, maturity_date=date(2033, 1, 15))

ALL_BONDS = [TEN_Y, FORTY_Y, SHORT, ZERO]


# ---------- day count ----------
@pytest.mark.parametrize(
    "d1,d2,conv,expected",
    [
        (date(2026, 1, 15), date(2026, 7, 15), "30/360", 180),
        (date(2026, 1, 31), date(2026, 3, 31), "30/360", 60),
        (date(2026, 1, 30), date(2026, 3, 31), "30U/360", 60),
        (date(2026, 1, 15), date(2026, 3, 31), "30U/360", 76),
        (date(2026, 1, 1), date(2026, 3, 1), "ACT/365", 59),
    ],
)
def test_day_count(d1, d2, conv, expected):
    assert day_count(d1, d2, conv) == expected


def test_unknown_day_count_raises():
    with pytest.raises(ValueError):
        day_count(date(2026, 1, 1), date(2026, 2, 1), "ACT/ACT")


# ---------- cash flows ----------
def test_cashflows_semiannual_schedule():
    cf = generate_cashflows(100, 0.0718, date(2036, 7, 15), SETTLE)
    assert cf["date"].iloc[0] == date(2026, 7, 15)
    assert cf["date"].iloc[-1] == date(2036, 7, 15)
    assert len(cf) == 21
    assert np.allclose(cf["coupon"], 3.59)
    assert cf["principal"].iloc[-1] == 100 and cf["principal"].iloc[:-1].sum() == 0
    assert cf["total"].iloc[-1] == pytest.approx(103.59)


def test_cashflows_month_end_clipping():
    cf = generate_cashflows(100, 0.07, date(2030, 3, 31), date(2029, 5, 1))
    assert list(cf["date"]) == [date(2029, 9, 30), date(2030, 3, 31)]


def test_settlement_on_coupon_date_excludes_that_coupon():
    cf = generate_cashflows(100, 0.0718, date(2036, 7, 15), date(2026, 7, 15))
    assert cf["date"].iloc[0] == date(2027, 1, 15)
    assert len(cf) == 20


def test_settlement_at_or_after_maturity_raises():
    with pytest.raises(ValueError):
        generate_cashflows(100, 0.07, date(2030, 1, 1), date(2030, 1, 1))


# ---------- accrued / price ----------
def test_accrued_zero_on_coupon_date():
    assert accrued_interest(TEN_Y, date(2026, 1, 15)) == 0.0
    assert accrued_interest(TEN_Y, date(2026, 7, 15)) == 0.0


def test_accrued_mid_period():
    # 15-Jan -> 10-Mar = 55 days (30/360); 3.59 * 55/180
    assert accrued_interest(TEN_Y, SETTLE) == pytest.approx(3.59 * 55 / 180)


@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y, SHORT])
def test_par_bond_on_coupon_date_prices_at_100(bond):
    settle = date(2026, 1, 15) if bond is not FORTY_Y else date(2025, 12, 19)
    assert clean_price(bond, settle, bond.coupon_rate) == pytest.approx(100, abs=1e-10)


@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y, SHORT])
def test_par_bond_mid_period_close_to_100(bond):
    # Street convention: between coupons a par-yield bond's clean price is ~100 but
    # not exactly (compounding vs linear accrual); gap is well under 5 paise.
    assert clean_price(bond, SETTLE, bond.coupon_rate) == pytest.approx(100, abs=0.05)


@pytest.mark.parametrize("bond", ALL_BONDS)
def test_price_falls_monotonically_as_yield_rises(bond):
    ys = np.linspace(0.001, 0.20, 80)
    prices = [dirty_price(bond, SETTLE, y) for y in ys]
    assert np.all(np.diff(prices) < 0)


@pytest.mark.parametrize("bond", ALL_BONDS)
@pytest.mark.parametrize("y", [0.03, 0.0712, 0.15])
def test_ytm_round_trip(bond, y):
    p = clean_price(bond, SETTLE, y)
    assert ytm(p, bond, SETTLE) == pytest.approx(y, abs=1e-10)


def test_ytm_non_convergence_raises_clear_error():
    with pytest.raises(YieldConvergenceError, match="Cannot solve YTM"):
        ytm(0.01, TEN_Y, SETTLE)


def test_ytm_rejects_bad_price():
    with pytest.raises(ValueError):
        ytm(-5.0, TEN_Y, SETTLE)


# ---------- duration / convexity ----------
def test_zero_coupon_duration_equals_time_to_maturity():
    assert macaulay_duration(ZERO, SETTLE, 0.07) == pytest.approx(
        year_fraction(SETTLE, ZERO.maturity_date), abs=1e-12
    )


def test_short_bond_duration_equals_time_to_maturity():
    # single remaining cash flow => behaves as a zero
    assert macaulay_duration(SHORT, SETTLE, 0.06) == pytest.approx(
        year_fraction(SETTLE, SHORT.maturity_date), abs=1e-12
    )


@pytest.mark.parametrize("bond", ALL_BONDS)
@pytest.mark.parametrize("y", [0.02, 0.07, 0.12])
def test_duration_convexity_dv01_match_finite_difference(bond, y):
    h = 1e-4  # 1bp
    p0 = dirty_price(bond, SETTLE, y)
    up, dn = dirty_price(bond, SETTLE, y + h), dirty_price(bond, SETTLE, y - h)
    fd_dur = (dn - up) / (2 * h * p0)
    fd_cvx = (up + dn - 2 * p0) / (h**2 * p0)
    assert modified_duration(bond, SETTLE, y) == pytest.approx(fd_dur, rel=1e-5)
    assert convexity(bond, SETTLE, y) == pytest.approx(fd_cvx, rel=1e-4)
    assert dv01(bond, SETTLE, y) == pytest.approx((dn - up) / 2, rel=1e-5)


def test_forty_year_bond_sane():
    d = modified_duration(FORTY_Y, SETTLE, 0.073)
    assert 11 < d < 14  # long G-sec at ~7% yield
    assert convexity(FORTY_Y, SETTLE, 0.073) > 200


# ---------- shock table ----------
def test_shock_table_shape_and_zero_row():
    t = yield_shock_table(TEN_Y, SETTLE, 0.07)
    assert list(t["shock_bps"]) == list(range(-100, 101, 25))
    zero = t[t["shock_bps"] == 0].iloc[0]
    assert zero["full_reval_pct"] == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize("bond", [TEN_Y, FORTY_Y])
def test_convexity_error_small_at_25bp_and_grows_at_100bp(bond):
    t = yield_shock_table(bond, SETTLE, 0.07).set_index("shock_bps")
    err = t["dur_convexity_err_pct"].abs()
    for s in (-25, 25):
        assert err[s] < 0.005  # < 0.5 bp of price
        assert err[s * 4] > 10 * err[s]  # third-order error grows ~64x
    # convexity term always improves on duration-only
    assert (t["dur_convexity_err_pct"].abs() <= t["duration_err_pct"].abs() + 1e-12).all()
    # duration alone understates price (positive convexity)
    assert (t["duration_err_pct"] <= 1e-12).all()
