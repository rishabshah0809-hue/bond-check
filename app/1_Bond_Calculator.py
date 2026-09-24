"""Bond Calculator — Phase 1. User-entered inputs only; not linked to market data."""

import sys
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pricing import (  # noqa: E402
    Bond,
    YieldConvergenceError,
    accrued_interest,
    bond_cashflows,
    clean_price,
    convexity,
    dirty_price,
    dv01,
    macaulay_duration,
    modified_duration,
    yield_shock_table,
    ytm,
)
from src.pricing.daycount import SUPPORTED  # noqa: E402

st.set_page_config(page_title="Bond Calculator", layout="wide")
st.title("Bond Calculator")
st.warning(
    "**ILLUSTRATIVE — not linked to market data.** All inputs are user-entered defaults, "
    "not live prices or yields. Output is modelled, not advice."
)

with st.sidebar:
    st.header("Bond")
    coupon_pct = st.number_input("Coupon (% p.a.)", 0.0, 30.0, 7.18, 0.01, format="%.4f")
    maturity = st.date_input("Maturity date", date(2036, 7, 15), max_value=date(2080, 12, 31))
    settle = st.date_input("Settlement date", date.today())
    day_count = st.selectbox("Day count", SUPPORTED, index=0)
    face = st.number_input("Face value (for DV01 in ₹)", 100.0, 1e10, 100.0, 100.0)
    st.header("Solve from")
    mode = st.radio("Input", ["Yield", "Clean price"], horizontal=True)
    if mode == "Yield":
        y_in = st.number_input("YTM (% p.a., semi-annual)", -10.0, 50.0, 7.00, 0.01, format="%.4f")
    else:
        p_in = st.number_input("Clean price (per 100)", 1.0, 500.0, 100.0, 0.01, format="%.4f")

if settle >= maturity:
    st.error("Settlement date must be before maturity.")
    st.stop()

bond = Bond(coupon_rate=coupon_pct / 100, maturity_date=maturity, day_count=day_count)
try:
    y = y_in / 100 if mode == "Yield" else ytm(p_in, bond, settle)
except YieldConvergenceError as e:
    st.error(str(e))
    st.stop()

scale = face / 100
metrics = {
    "Clean price": f"{clean_price(bond, settle, y):.4f}",
    "Dirty price": f"{dirty_price(bond, settle, y):.4f}",
    "Accrued interest": f"{accrued_interest(bond, settle):.4f}",
    "YTM": f"{y * 100:.4f}%",
    "Macaulay duration (y)": f"{macaulay_duration(bond, settle, y):.4f}",
    "Modified duration": f"{modified_duration(bond, settle, y):.4f}",
    "Convexity": f"{convexity(bond, settle, y):.4f}",
    f"DV01 (₹ per {face:,.0f} face)": f"{dv01(bond, settle, y) * scale:,.4f}",
}
cols = st.columns(4)
for i, (k, v) in enumerate(metrics.items()):
    cols[i % 4].metric(k, v)
st.caption("Prices per 100 face. Semi-annual compounding; street convention; see model docstrings.")

left, right = st.columns([1, 1])
with left:
    st.subheader("Yield-shock table")
    shocks = yield_shock_table(bond, settle, y)
    show = shocks.assign(**{"yield": shocks["yield"] * 100}).rename(
        columns={
            "shock_bps": "Shock (bp)",
            "yield": "Yield %",
            "full_price": "Dirty price",
            "full_reval_pct": "Full reval %",
            "duration_pct": "Duration %",
            "dur_convexity_pct": "Dur+Cvx %",
            "duration_err_pct": "Dur err (pp)",
            "dur_convexity_err_pct": "Dur+Cvx err (pp)",
        }
    )
    st.dataframe(show.style.format(precision=4), hide_index=True, width="stretch")
with right:
    st.subheader("Price change by method")
    fig = go.Figure()
    for col, name, dash in [
        ("full_reval_pct", "Full revaluation", "solid"),
        ("duration_pct", "Duration", "dot"),
        ("dur_convexity_pct", "Duration + convexity", "dash"),
    ]:
        fig.add_trace(
            go.Scatter(x=shocks["shock_bps"], y=shocks[col], name=name,
                       mode="lines+markers", line={"dash": dash})
        )
    fig.update_layout(xaxis_title="Yield shock (bp)", yaxis_title="Price change (%)",
                      height=420, legend={"orientation": "h", "y": -0.2})
    st.plotly_chart(fig, width="stretch")

st.subheader("Cash-flow schedule")
cf = bond_cashflows(bond, settle)
st.dataframe(cf.style.format(precision=4, subset=["coupon", "principal", "total"]),
             hide_index=True, width="stretch")
