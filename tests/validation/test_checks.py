"""Validation rule tests. Series values are ILLUSTRATIVE."""

from datetime import date

import numpy as np
import pandas as pd

from src.validation import (
    MISSING,
    OK,
    OUTLIER,
    STALE,
    assign_flags,
    duplicate_dates,
    missing_dates,
    outlier_mask,
    staleness,
)


def frame(values, start="2026-01-05"):
    d = pd.bdate_range(start, periods=len(values)).date
    return pd.DataFrame({"obs_date": d, "value": values})


def test_duplicate_dates():
    d = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 2)]
    assert duplicate_dates(d) == [date(2026, 1, 2)]
    assert duplicate_dates(d[:2]) == []


def test_missing_business_days():
    d = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 9)]  # Mon, Tue, Fri
    assert missing_dates(d, "D") == [date(2026, 1, 7), date(2026, 1, 8)]


def test_missing_monthly():
    d = [date(2025, 1, 1), date(2025, 2, 1), date(2025, 4, 1)]
    assert missing_dates(d, "M") == [date(2025, 3, 1)]


def test_staleness_by_frequency():
    today = date(2026, 6, 30)
    assert staleness(date(2026, 6, 26), "D", today) == (4, False)
    assert staleness(date(2026, 6, 1), "D", today) == (29, True)
    assert staleness(date(2026, 5, 1), "M", today) == (60, False)
    assert staleness(date(2025, 12, 1), "Q", today) == (211, True)
    assert staleness(None, "D", today) == (None, True)


def test_outlier_flags_jump_not_values():
    rng = np.random.default_rng(0)
    v = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.02, 60)))
    v[30] += 1.0  # spike: jump up at 30, back down at 31
    m = outlier_mask(v)
    assert m[30] and m.sum() <= 2
    assert v[30] > 4.5  # value untouched


def test_outlier_zero_mad_series_not_all_flagged():
    v = pd.Series([5.5] * 40 + [5.75] + [5.75] * 20)  # policy-rate style step
    m = outlier_mask(v)
    assert m.sum() <= 1


def test_outlier_ignores_nan():
    v = pd.Series([1.0, np.nan, 1.01, 1.02, np.nan, 1.01, 5.0])
    m = outlier_mask(v, min_changes=3)
    assert not m[v.isna()].any() and m.iloc[-1]


def test_assign_flags_priority_and_no_fill():
    vals = [4.0, 4.01, np.nan] + [4.02, 4.01, 4.03, 4.02] * 6 + [9.0]
    df = frame(vals)
    flags = assign_flags(df, "D", today=date(2026, 3, 1))  # far past -> stale
    assert flags.iloc[2] == MISSING
    assert flags.iloc[-1] == OUTLIER  # outlier beats stale on the last row
    assert (flags.iloc[[0, 1, 3]] == OK).all()
    assert np.isnan(df["value"].iloc[2])  # input not modified


def test_assign_flags_stale_on_last_valid_only():
    df = frame([4.0, 4.01, 4.02, 4.01, np.nan])
    flags = assign_flags(df, "D", today=date(2026, 2, 1))
    assert flags.iloc[3] == STALE and flags.iloc[4] == MISSING
    assert (flags.iloc[:3] == OK).all()


def test_outlier_needs_minimum_history():
    v = pd.Series([4.0, 4.01, 4.0, 4.02, 9.0])
    assert not outlier_mask(v).any()
    assert outlier_mask(v, min_changes=3).iloc[-1]
