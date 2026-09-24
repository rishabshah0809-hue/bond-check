"""Curve engine tests. All curves are ILLUSTRATIVE (synthetic), not market data."""

import io
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.curves import (
    FlatCurve,
    NSSCurve,
    curve_table_from_store,
    fit_curve_table,
    fit_nss,
    read_curve_csv,
    split_by_date,
    store_curve_dates,
    store_curve_ids,
)
from src.ingestion import golden_store as gs

# ILLUSTRATIVE "true" NSS curve
TRUE = NSSCurve(b0=0.072, b1=-0.015, b2=0.01, b3=-0.005, tau1=1.8, tau2=9.0)
TENORS = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40])


def test_nss_limits():
    assert TRUE.zero(1e-9) == pytest.approx(TRUE.b0 + TRUE.b1, abs=1e-8)
    assert TRUE.zero(1e6) == pytest.approx(TRUE.b0, abs=1e-5)


def test_fit_recovers_known_parameters_noise_free():
    fit = fit_nss(TENORS, TRUE.zero(TENORS), rate_type="zero")
    assert fit.method == "NSS" and fit.converged
    assert fit.rmse_bps < 1e-4 and fit.max_abs_error_bps < 1e-3
    for k, v in TRUE.params.items():
        assert fit.params[k] == pytest.approx(v, rel=1e-3, abs=1e-5), k


def test_fit_par_inputs_recovers_zero_curve():
    fit = fit_nss(TENORS, TRUE.par_yield(TENORS), rate_type="par")
    assert fit.rmse_bps < 1e-3
    grid = np.linspace(0.25, 40, 50)
    assert np.max(np.abs(fit.curve.zero(grid) - TRUE.zero(grid))) < 1e-6


def test_fit_with_half_bp_noise_keeps_rmse_small():
    rng = np.random.default_rng(1)
    noisy = TRUE.zero(TENORS) + rng.uniform(-0.5e-4, 0.5e-4, len(TENORS))
    fit = fit_nss(TENORS, noisy, rate_type="zero")
    assert fit.rmse_bps < 0.5
    assert fit.max_abs_error_bps < 1.0


def test_fit_is_deterministic():
    noisy = TRUE.zero(TENORS) + np.random.default_rng(2).normal(0, 2e-4, len(TENORS))
    a, b = fit_nss(TENORS, noisy, "zero"), fit_nss(TENORS, noisy, "zero")
    assert a.params == b.params


# ---------- degenerate input ----------
def test_too_few_points_rejected():
    with pytest.raises(ValueError, match=">= 4"):
        fit_nss([1, 2, 5], [0.07, 0.071, 0.072])


def test_four_or_five_points_fall_back_to_ns():
    fit = fit_nss([1, 2, 5, 10], [0.065, 0.068, 0.07, 0.071])
    assert fit.method == "NS" and fit.params["b3"] == 0.0
    assert any("fell back" in w for w in fit.warnings)


def test_duplicate_tenors_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        fit_nss([1, 2, 2, 5, 10, 30], [0.06, 0.062, 0.063, 0.065, 0.07, 0.072])


def test_non_monotone_tenors_sorted_and_flagged():
    t = TENORS[::-1]
    fit = fit_nss(t, TRUE.zero(t), "zero")
    assert np.all(np.diff(fit.tenors) > 0)
    assert any("sorted" in w for w in fit.warnings)
    assert fit.rmse_bps < 1e-3


def test_nonpositive_tenor_rejected():
    with pytest.raises(ValueError, match="> 0"):
        fit_nss([0, 1, 2, 5, 10, 30], [0.06] * 6)


def test_missing_points_dropped_not_filled():
    obs = TRUE.zero(TENORS).copy()
    obs[3] = np.nan
    fit = fit_nss(TENORS, obs, "zero")
    assert fit.n_dropped == 1 and len(fit.tenors) == len(TENORS) - 1
    assert 2.0 not in fit.tenors


def test_unstable_nss_falls_back_to_ns():
    # a pure NS curve has no second hump -> NSS b3/tau2 unidentified
    ns = NSSCurve(0.07, -0.01, 0.0, 0.0, 2.0, 7.0)
    fit = fit_nss(TENORS, ns.zero(TENORS), "zero")
    assert fit.rmse_bps < 0.01
    if fit.method == "NS":
        assert any("fell back" in w for w in fit.warnings)


# ---------- curve object ----------
def test_flat_curve_discount_factors_closed_form():
    r = 0.07
    t = np.array([0.5, 1, 5, 30])
    assert np.allclose(FlatCurve(r).discount_factor(t), np.exp(-r * t), atol=1e-15)
    y = 0.0712
    assert np.allclose(FlatCurve.from_semiannual(y).discount_factor(t),
                       (1 + y / 2) ** (-2 * t), atol=1e-14)
    assert FlatCurve.from_semiannual(y).zero_rate(3, "semiannual") == pytest.approx(y)


def test_forward_rate():
    assert FlatCurve(0.07).forward_rate(1, 2) == pytest.approx(0.07)
    f = TRUE.forward_rate(2, 5)
    assert np.exp(-f * 3) == pytest.approx(TRUE.discount(5) / TRUE.discount(2))
    with pytest.raises(ValueError):
        TRUE.forward_rate(5, 2)


def test_par_yield_of_flat_curve():
    r = 0.07
    assert FlatCurve(r).par_yield(10.0) == pytest.approx(2 * np.expm1(r / 2), abs=1e-12)


# ---------- inputs: CSV + store ----------
def test_read_curve_csv_and_fit():
    csv = "tenor_years,yield_pct,note\n" + "\n".join(
        f"{t},{y * 100}," for t, y in zip(TENORS, TRUE.par_yield(TENORS), strict=True)
    )
    table = read_curve_csv(io.StringIO(csv))
    fit = fit_curve_table(table, date(2026, 9, 25), rate_type="par")
    assert fit.curve_date == date(2026, 9, 25) and fit.rmse_bps < 1e-3


def test_read_curve_csv_with_dates_splits_by_date():
    csv = (
        "tenor_years,yield_pct,date\n"
        "1,6.0,2026-09-24\n5,6.5,2026-09-24\n1,6.1,2026-09-25\n"
    )
    table = read_curve_csv(io.StringIO(csv))
    parts = split_by_date(table)
    assert list(parts) == [date(2026, 9, 25), date(2026, 9, 24)]  # newest first
    assert list(parts[date(2026, 9, 24)]["yield_pct"]) == [6.0, 6.5]


def test_read_curve_csv_bad_date_rejected():
    with pytest.raises(ValueError, match="date"):
        read_curve_csv(io.StringIO("tenor_years,yield_pct,date\n1,6.0,notadate\n"))


def test_read_curve_csv_bad_columns():
    with pytest.raises(ValueError, match="missing column"):
        read_curve_csv(io.StringIO("tenor,yield\n1,6.5\n"))


def test_store_curve_roundtrip(tmp_path):
    con = gs.connect(tmp_path / "g.duckdb")
    assert store_curve_ids(con) == []
    d = date(2026, 9, 24)
    rows = pd.DataFrame(
        {
            "series_id": [f"TEST_CURVE_{t:g}Y" for t in TENORS] + ["DGS10"],
            "obs_date": [d] * (len(TENORS) + 1),
            "value": list(TRUE.zero(TENORS) * 100) + [4.1],
            "source": "TEST", "frequency": "D", "quality_flag": "OK",
            "retrieved_at": pd.Timestamp("2026-09-25"), "raw_file_path": None,
            "transformation": None,
        }
    )
    gs.upsert_observations(con, rows)
    assert store_curve_ids(con) == ["TEST_CURVE"]
    assert store_curve_dates(con, "TEST_CURVE") == [d]
    table = curve_table_from_store(con, "TEST_CURVE", d)
    assert list(table["tenor_years"]) == list(TENORS)
    assert curve_table_from_store(con, "TEST_CURVE", date(2020, 1, 1)).empty
    con.close()
