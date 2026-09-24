"""Yield Curve — fit NSS/NS to a curve table; compare dates when history exists."""

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.curve_input import (  # noqa: E402
    ILLUSTRATIVE_MSG,
    curve_source_sidebar,
    date_label,
    fit_source,
    remember,
)

st.set_page_config(page_title="Yield Curve", layout="wide")
st.title("Yield Curve")
st.caption("Modelled curve, not advice. Missing points are dropped, never filled.")

src = curve_source_sidebar()
if src is None:
    st.stop()
if src.illustrative:
    st.warning(ILLUSTRATIVE_MSG + " Upload your own curve CSV to replace it.")
if not src.tables:
    st.info("The selected store curve has no non-missing points.")
    st.stop()

dates = list(src.tables)
curve_date = dates[0]
if len(dates) > 1:
    curve_date = st.selectbox("Curve date", dates, format_func=date_label)

try:
    fit = fit_source(src, curve_date)
except ValueError as e:
    st.error(f"Cannot fit curve: {e}")
    st.stop()
remember(fit, src)
st.caption(f"Source: {src.label} · date {date_label(curve_date)} · used by the Bond Calculator.")
for w in fit.warnings:
    st.warning(w)

c = fit.curve
m = st.columns(6)
m[0].metric("Level β0", f"{c.b0 * 100:.3f}%")
m[1].metric("Slope β1", f"{c.b1 * 100:.3f}%")
m[2].metric("Curvature β2", f"{c.b2 * 100:.3f}%")
m[3].metric("RMSE", f"{fit.rmse_bps:.2f} bp")
m[4].metric("Max |error|", f"{fit.max_abs_error_bps:.2f} bp")
m[5].metric("Method", f"{fit.method}{'' if fit.converged else ' (not converged)'}")
p = fit.params
extra = f"β3 = {p['b3'] * 100:.3f}%, τ2 = {p['tau2']:.2f}, " if fit.method == "NSS" else ""
st.caption(
    f"{extra}τ1 = {p['tau1']:.2f}. Inputs: {fit.rate_type} yields. "
    "Zero rates continuously compounded; par yields semi-annual."
)

grid = np.linspace(0.1, max(40.0, float(fit.tenors.max())), 200)
fig = go.Figure()
fig.add_trace(go.Scatter(x=fit.tenors, y=fit.observed * 100, mode="markers",
                         name=f"Observed ({fit.rate_type})", marker={"size": 9}))
fig.add_trace(go.Scatter(x=grid, y=c.zero_rate(grid) * 100, name="Fitted zero (cont.)"))
fig.add_trace(go.Scatter(x=grid, y=c.par_yield(grid) * 100, name="Fitted par (s.a.)",
                         line={"dash": "dash"}))

others = [d for d in dates if d != curve_date]
if others:
    compare = st.multiselect("Compare with", others, default=others[:2], format_func=date_label)
    for d in compare:
        try:
            f2 = fit_source(src, d)
        except ValueError as e:
            st.warning(f"{date_label(d)}: {e}")
            continue
        y2 = f2.curve.par_yield(grid) if src.rate_type == "par" else f2.curve.zero_rate(grid)
        fig.add_trace(go.Scatter(x=grid, y=y2 * 100, name=f"{date_label(d)} ({src.rate_type})",
                                 line={"dash": "dot"}))
else:
    st.caption("Curve history comparison appears when the source holds more than one date.")

fig.update_layout(xaxis_title="Tenor (years)", yaxis_title="Yield (%)", height=440,
                  legend={"orientation": "h", "y": -0.2})
st.plotly_chart(fig, width="stretch")

st.subheader("Fit errors")
st.dataframe(
    fit.error_table().style.format(
        {"tenor_years": "{:g}", "observed_pct": "{:.4f}", "fitted_pct": "{:.4f}",
         "error_bp": "{:+.2f}"}
    ),
    hide_index=True,
    width="stretch",
)
