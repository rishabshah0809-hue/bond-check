"""Data-quality checks. Checks FLAG data; they never fill, interpolate or delete values.

Flags (one per row, highest priority wins): MISSING > OUTLIER > STALE > OK.
- MISSING: the source published the date with no value (stored as NULL).
- OUTLIER: robust z-score of the change from the previous non-missing observation
  exceeds ``threshold`` (default 6). z = 0.6745 * (x - median) / MAD. If MAD == 0
  (e.g. a policy rate that rarely moves) falls back to 1.2533 * mean absolute
  deviation; if that is also 0 nothing is flagged. The LATER observation of the jump
  is flagged. Changes are between consecutive observations whatever the frequency.
  Needs >= ``min_changes`` (default 20) changes; shorter histories get no OUTLIER flags.
- STALE: the latest non-missing observation is older than the frequency's allowance
  (see STALE_AFTER_DAYS); only that last observation is flagged.
Duplicate dates and missing calendar dates are reported, not written as flags:
duplicates are rejected before loading; gaps are listed by ``missing_dates``.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

OK, STALE, OUTLIER, MISSING = "OK", "STALE", "OUTLIER", "MISSING"

# Allowed age (calendar days) of the latest observation, measured from obs_date.
# Monthly/quarterly obs_dates are period STARTS (FRED convention) and are published
# weeks after the period ends, hence the long allowances.
STALE_AFTER_DAYS = {"D": 7, "W": 14, "M": 75, "Q": 200}

_EXPECTED_FREQ = {"D": "B", "W": "W", "M": "MS", "Q": "QS"}


def duplicate_dates(dates: pd.Series) -> list:
    """Dates that occur more than once."""
    d = pd.Series(dates)
    return sorted(d[d.duplicated(keep=False)].unique().tolist())


def missing_dates(dates: pd.Series, frequency: str) -> list[date]:
    """Expected dates between first and last that are absent.

    Daily series expect business days (Mon-Fri); exchange holidays therefore show up as
    gaps (no holiday calendar is applied). Weekly gaps are checked only by count.
    """
    d = pd.to_datetime(pd.Series(dates)).dropna()
    if d.empty or frequency not in _EXPECTED_FREQ:
        return []
    if frequency == "W":
        expected = pd.date_range(d.min(), d.max(), freq="7D")
    else:
        expected = pd.date_range(d.min(), d.max(), freq=_EXPECTED_FREQ[frequency])
    return [x.date() for x in expected.difference(pd.DatetimeIndex(d))]


def staleness(last_date: date | None, frequency: str, today: date) -> tuple[int | None, bool]:
    """(age in days, is_stale) for the latest valid observation. None date -> stale."""
    if last_date is None:
        return None, True
    age = (today - pd.Timestamp(last_date).date()).days
    return age, age > STALE_AFTER_DAYS.get(frequency, 7)


def outlier_mask(
    values: pd.Series, threshold: float = 6.0, min_changes: int = 20
) -> pd.Series:
    """Boolean mask (same index) marking observations whose change is a robust outlier.

    NaN values are skipped and never flagged; changes are taken between consecutive
    non-missing values.
    """
    v = values.dropna()
    mask = pd.Series(False, index=values.index)
    if len(v) - 1 < min_changes:
        return mask
    ch = v.diff().iloc[1:]
    med = ch.median()
    dev = (ch - med).abs()
    scale = dev.median() / 0.6745
    if scale == 0:
        scale = dev.mean() * 1.2533
    if scale == 0 or not np.isfinite(scale):
        return mask
    z = (ch - med) / scale
    mask.loc[z.index[z.abs() > threshold]] = True
    return mask


def assign_flags(
    df: pd.DataFrame, frequency: str, today: date, threshold: float = 6.0
) -> pd.Series:
    """Quality flag per row of ``df`` (columns obs_date, value), indexed like ``df``."""
    df = df.sort_values("obs_date")
    flags = pd.Series(OK, index=df.index)
    valid = df["value"].notna()
    if valid.any():
        last_idx = df.index[valid][-1]
        _, stale = staleness(df.loc[last_idx, "obs_date"], frequency, today)
        if stale:
            flags[last_idx] = STALE
    flags[outlier_mask(df["value"], threshold)] = OUTLIER
    flags[~valid] = MISSING
    return flags
