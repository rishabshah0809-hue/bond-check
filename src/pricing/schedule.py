"""Bond definition and coupon schedule generation.

Conventions (Indian G-sec defaults):
- Fixed coupon paid ``freq`` times a year (default 2) on dates rolled back from maturity
  in 12/freq-month steps. Day-of-month follows maturity, clipped to month length
  (maturity 31-Mar -> 30-Sep, 31-Mar). No business-day adjustment.
- Coupon per period = face * coupon_rate / freq (fixed, independent of day count).
- Stub handling: the schedule is anchored to maturity, so settlement mid-period gives a
  fractional first period (fraction computed in pricing.py). Irregular first coupons
  from the issue date (long/short first coupon) are NOT modelled.
- A coupon falling on the settlement date is NOT received by the buyer; the first
  cash flow is the next one.
- Record-date / shut-period (ex-interest) effects are ignored.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.pricing.daycount import DEFAULT_DAY_COUNT, SUPPORTED


@dataclass(frozen=True)
class Bond:
    """Fixed-coupon bullet bond. ``coupon_rate`` is a decimal (7.18% -> 0.0718)."""

    coupon_rate: float
    maturity_date: date
    face: float = 100.0
    freq: int = 2
    day_count: str = DEFAULT_DAY_COUNT

    def __post_init__(self) -> None:
        if self.face <= 0:
            raise ValueError("face must be positive")
        if self.coupon_rate < 0:
            raise ValueError("coupon_rate must be >= 0")
        if self.freq not in (1, 2, 4, 12):
            raise ValueError("freq must be 1, 2, 4 or 12")
        if self.day_count not in SUPPORTED:
            raise ValueError(f"day_count must be one of {SUPPORTED}")


def add_months(d: date, months: int, anchor_day: int | None = None) -> date:
    """Shift ``d`` by ``months``; day = ``anchor_day`` (default d.day) clipped to month end."""
    total = d.year * 12 + (d.month - 1) + months
    y, m0 = divmod(total, 12)
    m = m0 + 1
    return date(y, m, min(anchor_day or d.day, calendar.monthrange(y, m)[1]))


def coupon_dates(bond: Bond, settlement_date: date) -> tuple[date, list[date]]:
    """Return (previous coupon date, future coupon dates up to and incl. maturity).

    Future dates are strictly after settlement; the previous date is <= settlement
    (equal when settling on a coupon date). Raises ValueError if settlement >= maturity.
    """
    if settlement_date >= bond.maturity_date:
        raise ValueError("settlement_date must be before maturity_date")
    step = 12 // bond.freq
    anchor = bond.maturity_date.day
    future = [bond.maturity_date]
    k = 1
    while True:
        d = add_months(bond.maturity_date, -step * k, anchor)
        if d <= settlement_date:
            return d, future[::-1]
        future.append(d)
        k += 1


def bond_cashflows(bond: Bond, settlement_date: date) -> pd.DataFrame:
    """Future cash flows for a buyer settling on ``settlement_date``.

    Columns: date, coupon, principal, total (currency per ``bond.face``).
    """
    _, dates = coupon_dates(bond, settlement_date)
    cpn = bond.face * bond.coupon_rate / bond.freq
    df = pd.DataFrame(
        {
            "date": dates,
            "coupon": [cpn] * len(dates),
            "principal": [bond.face if d == bond.maturity_date else 0.0 for d in dates],
        }
    )
    df["total"] = df["coupon"] + df["principal"]
    return df


def generate_cashflows(
    face: float,
    coupon_rate: float,
    maturity_date: date,
    settlement_date: date,
    freq: int = 2,
) -> pd.DataFrame:
    """Future cash flows (semi-annual by default); see module docstring for conventions."""
    bond = Bond(coupon_rate=coupon_rate, maturity_date=maturity_date, face=face, freq=freq)
    return bond_cashflows(bond, settlement_date)
