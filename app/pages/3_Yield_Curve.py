"""Yield Curve — Phase 2. User-entered or uploaded curve points; not linked to market data."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.curves import fit_nss  # noqa: E402
from src.pricing import Bond  # noqa: E402
from src.pricing.curve_risk import (  # noqa: E402
    carry_rolldown,
    curve_clean_price,
    curve_dirty_price,
    key_rate_durations,
)
from src.pricing.pricing import accrued_interest, ytm  # noqa: E402

st.set_page_config(page_title="Yield Curve", layout="wide")
st.title("Yield Curve")
st.warning(
    "**ILLUSTRATIVE — not linked to market data.** Default curve points are made up for "
    "demonstration. Enter or upload official (e.g. FBIL) values yourself. Output is modelled, "
    "not advice."
)

# ILLUSTRATIVE default points (not market data)
DEFAULT = pd.DataFrame(
    {
        "tenor_years": [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40],
        "yield_pct": [5.60, 5.70, 5.80, 6.00, 6.15, 6.35, 6.50, 6.65, 6.85, 6.95, 7.05, 7.08],
    }
)

with st.sidebar:
    st.header("Curve input")
    rate_type = st.radio("Input yields are", ["par", "zero"], horizontal=True,
                         help="par = semi-annual par yields; zero = continuously compounded")
    model = st.radio("Model", ["NSS", "NS"], horizontal=True)
    upload = st.file_uploader("Upload CSV (tenor_years, yield_pct)", type="csv")

base = DEFAULT
if upload is not None:
    try:
        base = pd.read_csv(upload)[["tenor_years", "yield_pct"]]
    except (KeyError, ValueError) as e:
        st.error(f"CSV must have columns tenor_years, yield_pct ({e})")
        st.stop()

st.subheader("Curve points")
pts = st.data_editor(base, num_rows="dynamic", width="stretch", key="pts")
t = pd.to_numeric(pts["tenor_years"], errors="coerce").to_numpy()
r = pd.to_numeric(pts["yield_pct"], errors="coerce").to_numpy() / 100

try:
    fit = fit_nss(t, r, rate_type=rate_type, model=model)
except ValueError as e:
    st.error(str(e))
    st.stop()
c = fit.curve
if fit.n_dropped:
    st.info(f"{fit.n_dropped} missing/invalid point(s) ignored (not filled).")

cols = st.columns(4)
cols[0].metric("Level β0", f"{c.b0 * 100:.3f}%")
cols[1].metric("Slope β1", f"{c.b1 * 100:.3f}%")
cols[2].metric("Curvature β2", f"{c.b2 * 100:.3f}%")
cols[3].metric("Fit RMSE", f"{fit.rmse_bps:.2f} bp")
extra = f"β3 = {c.b3 * 100:.3f}%, τ2 = {c.tau2:.2f}, " if model == "NSS" else ""
st.caption(f"{extra}τ1 = {c.tau1:.2f}. Zero rates continuously compounded; par semi-annual.")

grid = np.linspace(0.1, max(40.0, float(np.nanmax(t))), 200)
fig = go.Figure()
fig.add_trace(go.Scatter(x=fit.tenors, y=fit.observed * 100, mode="markers",
                         name=f"Input ({rate_type})", marker={"size": 9}))
fig.add_trace(go.Scatter(x=grid, y=c.zero(grid) * 100, name="Fitted zero"))
fig.add_trace(go.Scatter(x=grid, y=c.par_yield(grid) * 100, name="Fitted par",
                         line={"dash": "dash"}))
fig.update_layout(xaxis_title="Tenor (years)", yaxis_title="Yield (%)", height=420,
                  legend={"orientation": "h", "y": -0.2})
st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Bond off the fitted curve")
b1, b2, b3 = st.columns(3)
coupon_pct = b1.number_input("Coupon (% p.a.)", 0.0, 30.0, 7.18, 0.01, format="%.4f")
maturity = b2.date_input("Maturity date", date(2036, 7, 15), max_value=date(2080, 12, 31))
settle = b3.date_input("Settlement date", date.today())
if settle >= maturity:
    st.error("Settlement date must be before maturity.")
    st.stop()
bond = Bond(coupon_rate=coupon_pct / 100, maturity_date=maturity)

clean = curve_clean_price(bond, settle, c)
m = st.columns(4)
m[0].metric("Clean price", f"{clean:.4f}")
m[1].metric("Dirty price", f"{curve_dirty_price(bond, settle, c):.4f}")
m[2].metric("Accrued", f"{accrued_interest(bond, settle):.4f}")
m[3].metric("Implied YTM", f"{ytm(clean, bond, settle) * 100:.4f}%")

left, right = st.columns(2)
with left:
    st.markdown("**Key-rate durations**")
    krd = key_rate_durations(bond, settle, c)
    kfig = go.Figure(go.Bar(x=[f"{k:g}Y" for k in krd.index], y=krd.values))
    kfig.update_layout(yaxis_title="Duration (years)", height=320,
                       margin={"t": 10})
    st.plotly_chart(kfig, width="stretch")
    st.caption(f"Sum = {krd.sum():.4f} (parallel duration vs continuous zero rates).")
with right:
    st.markdown("**12-month carry & roll-down (curve unchanged)**")
    try:
        cr = carry_rolldown(bond, settle, c)
        st.dataframe(
            pd.DataFrame(
                {
                    "Component": ["Carry", "Roll-down", "Total"],
                    "Per 100 face": [cr["carry"], cr["rolldown"], cr["total"]],
                    "% of dirty": [cr["carry_pct"], cr["rolldown_pct"], cr["total_pct"]],
                }
            ).style.format(precision=4),
            hide_index=True,
            width="stretch",
        )
        st.caption("No funding cost; coupons not reinvested; static curve in tenor space.")
    except ValueError:
        st.markdown("—  \n*Bond matures within the 12-month horizon.*")
