"""Day-count conventions.

Supported:
- "30/360"  : 30E/360 (Eurobond basis): day 31 -> 30 on both dates. Default, used for
              Indian G-secs/SDLs. OPEN QUESTION: exact 30/360 variant (30E vs US/ISDA,
              end-of-February handling) to be confirmed against FBIL/CCIL.
- "30U/360" : US (NASD) 30/360: D2=31 -> 30 only if D1 >= 30.
- "ACT/365" : actual days / 365 (fixed). Provided for T-bills / comparison.
"""

from __future__ import annotations

from datetime import date

DEFAULT_DAY_COUNT = "30/360"
SUPPORTED = ("30/360", "30U/360", "ACT/365")


def day_count(d1: date, d2: date, convention: str = DEFAULT_DAY_COUNT) -> int:
    """Days between d1 and d2 under ``convention`` (positive when d2 > d1).

    Assumption: 30/360 variants apply no end-of-February adjustment.
    """
    if convention == "ACT/365":
        return (d2 - d1).days
    day1, day2 = d1.day, d2.day
    if convention == "30/360":
        day1, day2 = min(day1, 30), min(day2, 30)
    elif convention == "30U/360":
        day1 = min(day1, 30)
        if day2 == 31 and day1 == 30:
            day2 = 30
    else:
        raise ValueError(f"Unsupported day count {convention!r}; use one of {SUPPORTED}")
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (day2 - day1)


def year_fraction(d1: date, d2: date, convention: str = DEFAULT_DAY_COUNT) -> float:
    """Year fraction: days/360 for 30/360 variants, days/365 for ACT/365."""
    basis = 365 if convention == "ACT/365" else 360
    return day_count(d1, d2, convention) / basis
