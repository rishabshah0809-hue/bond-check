"""Shared Streamlit curve-input widget (not a page: lives outside app/pages/).

Modes: (a) golden store, shown only if it holds a curve; (b) manual CSV upload
(tenor_years, yield_pct[, date]); plus an ILLUSTRATIVE sample so the pages work empty.
The chosen, fitted curve is kept in st.session_state["active_curve"] so the Bond
Calculator's curve tab uses the same curve as the Yield Curve page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from src.curves import (
    NSSFit,
    curve_table_from_store,
    fit_curve_table,
    read_curve_csv,
    split_by_date,
    store_curve_dates,
    store_curve_ids,
)
from src.ingestion.golden_store import DEFAULT_DB, connect

# ILLUSTRATIVE sample par curve — made-up numbers, NOT market data.
SAMPLE = pd.DataFrame(
    {
        "tenor_years": [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40],
        "yield_pct": [5.60, 5.70, 5.80, 6.00, 6.15, 6.35, 6.50, 6.65, 6.85, 6.95, 7.05, 7.08],
    }
)
ILLUSTRATIVE_MSG = "**ILLUSTRATIVE sample curve — made-up numbers, not market data.**"
CSV_HELP = (
    "Columns: tenor_years, yield_pct (percent), optional date (YYYY-MM-DD). "
    "Upload your own licensed data (e.g. FBIL par or zero curve)."
)


@dataclass
class CurveSource:
    """Tables by curve date (newest first), where they came from, and fit settings."""

    tables: dict  # {date|None: DataFrame}
    label: str
    illustrative: bool
    rate_type: str
    model: str


def _store_curves() -> list[str]:
    if not DEFAULT_DB.exists():
        return []
    try:
        con = connect(DEFAULT_DB, read_only=True)
        try:
            return store_curve_ids(con)
        finally:
            con.close()
    except Exception:  # locked/corrupt store: behave as if empty
        return []


def curve_source_sidebar() -> CurveSource | None:
    """Sidebar controls; returns the selected source or None (with an error shown)."""
    st.sidebar.header("Curve input")
    store_ids = _store_curves()
    modes = (["Golden store"] if store_ids else []) + ["Upload CSV", "ILLUSTRATIVE sample"]
    mode = st.sidebar.radio("Source", modes, key="curve_mode")
    rate_type = st.sidebar.radio(
        "Input yields are", ["par", "zero"], horizontal=True, key="curve_rate_type",
        help="par = semi-annual par yields; zero = continuously-compounded zero rates",
    )
    model = st.sidebar.radio("Model", ["NSS", "NS"], horizontal=True, key="curve_model")

    if mode == "Golden store":
        cid = st.sidebar.selectbox("Curve", store_ids)
        con = connect(DEFAULT_DB, read_only=True)
        try:
            dates = store_curve_dates(con, cid)
            tables = {d: curve_table_from_store(con, cid, d) for d in dates}
        finally:
            con.close()
        return CurveSource(tables, f"Golden store: {cid}", False, rate_type, model)

    if mode == "Upload CSV":
        up = st.sidebar.file_uploader("Curve CSV", type="csv", help=CSV_HELP, key="curve_csv")
        if up is None:
            st.info(f"Upload a curve CSV in the sidebar. {CSV_HELP}")
            return None
        try:
            tables = split_by_date(read_curve_csv(up))
        except ValueError as e:
            st.error(str(e))
            return None
        return CurveSource(tables, f"Upload: {up.name}", False, rate_type, model)

    return CurveSource({None: SAMPLE}, "ILLUSTRATIVE sample", True, rate_type, model)


def fit_source(src: CurveSource, curve_date: date | None) -> NSSFit:
    """Fit the table for ``curve_date`` (ValueError propagates for degenerate input)."""
    return fit_curve_table(src.tables[curve_date], curve_date, src.rate_type, src.model)


def remember(fit: NSSFit, src: CurveSource) -> None:
    st.session_state["active_curve"] = {
        "fit": fit, "label": src.label, "illustrative": src.illustrative
    }


def active_curve() -> dict | None:
    return st.session_state.get("active_curve")


def date_label(d: date | None) -> str:
    return "—" if d is None else d.isoformat()
