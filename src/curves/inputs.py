"""Curve inputs: a plain table (tenor_years, yield_pct) plus a curve date.

Sources
(a) Golden store: observations whose series_id is "{curve_id}_{tenor}Y", e.g.
    "IN_GSEC_PAR_10Y", "IN_GSEC_PAR_0.25Y". The tenor is parsed from the suffix; value is
    the yield in PERCENT. No India curve series exist yet (see docs/india_data_sources.md),
    so these functions return empty results until an ingestion adds them.
(b) Manual CSV upload with columns tenor_years, yield_pct and optional date (ISO
    YYYY-MM-DD). With a date column one file may hold several curve dates (history).
    Other columns are ignored. Users supply their own (e.g. FBIL-licensed) data.

Nothing here fills, interpolates or invents points; missing yields stay NaN and the
fitter drops them with a warning.
"""

from __future__ import annotations

import re
from datetime import date

import duckdb
import pandas as pd

from src.curves.nss import NSSFit, fit_nss

COLUMNS = ["tenor_years", "yield_pct"]
_TENOR_RE = re.compile(r"_(\d+(?:\.\d+)?)Y$")


def _pattern(curve_id: str) -> str:
    return "^" + re.escape(curve_id) + r"_\d+(\.\d+)?Y$"


def read_curve_csv(file) -> pd.DataFrame:
    """Read a CSV into columns tenor_years, yield_pct[, curve_date]. ValueError if bad.

    Non-numeric yields become NaN (dropped later by the fitter, never filled). An
    unparseable date is an error (a curve must not be attached to a guessed date).
    """
    df = pd.read_csv(file)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing column(s) {missing}; need {COLUMNS} (+ optional date)")
    out = df[COLUMNS].apply(pd.to_numeric, errors="coerce")
    if "date" in df.columns:
        d = pd.to_datetime(df["date"], errors="coerce", format="ISO8601")
        if d.isna().any():
            bad = df.loc[d.isna(), "date"].head(3).tolist()
            raise ValueError(f"unparseable date value(s) {bad}; use YYYY-MM-DD")
        out["curve_date"] = d.dt.date
    return out


def split_by_date(table: pd.DataFrame) -> dict:
    """{curve_date: table} newest first; a table without dates maps to {None: table}."""
    if "curve_date" not in table.columns:
        return {None: table[COLUMNS]}
    return {
        d: g[COLUMNS].reset_index(drop=True)
        for d, g in sorted(table.groupby("curve_date"), key=lambda x: x[0], reverse=True)
    }


def fit_curve_table(
    table: pd.DataFrame, curve_date: date | None, rate_type: str = "par", model: str = "NSS"
) -> NSSFit:
    """Fit a curve to a (tenor_years, yield_pct) table; yields are in percent."""
    t = pd.to_numeric(table["tenor_years"], errors="coerce").to_numpy()
    y = pd.to_numeric(table["yield_pct"], errors="coerce").to_numpy() / 100.0
    return fit_nss(t, y, rate_type=rate_type, model=model, curve_date=curve_date)


def store_curve_ids(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Curve ids present in the store (series ids ending in _<tenor>Y)."""
    ids = con.execute("SELECT DISTINCT series_id FROM observations").fetchall()
    return sorted({_TENOR_RE.sub("", s) for (s,) in ids if _TENOR_RE.search(s)})


def store_curve_dates(con: duckdb.DuckDBPyConnection, curve_id: str) -> list[date]:
    """Dates with at least one non-missing point for ``curve_id``, newest first."""
    rows = con.execute(
        """SELECT DISTINCT obs_date FROM observations
           WHERE regexp_matches(series_id, ?) AND value IS NOT NULL
           ORDER BY obs_date DESC""",
        [_pattern(curve_id)],
    ).fetchall()
    return [r[0] for r in rows]


def curve_table_from_store(
    con: duckdb.DuckDBPyConnection, curve_id: str, curve_date: date
) -> pd.DataFrame:
    """Standard table for one curve date (empty if none). NULL values stay NaN."""
    rows = con.execute(
        "SELECT series_id, value FROM observations"
        " WHERE regexp_matches(series_id, ?) AND obs_date = ?",
        [_pattern(curve_id), curve_date],
    ).fetchall()
    recs = []
    for sid, v in rows:
        m = _TENOR_RE.search(sid)
        if m:
            recs.append({"tenor_years": float(m.group(1)), "yield_pct": v})
    df = pd.DataFrame(recs, columns=COLUMNS).astype(float)
    return df.sort_values("tenor_years", ignore_index=True)
