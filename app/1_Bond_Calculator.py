"""Bond Calculator — Phase 1. User-entered inputs only; not linked to market data."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.curve_input import ILLUSTRATIVE_MSG, SAMPLE, active_curve  # noqa: E402
from src.curves import fit_curve_table  # noqa: E402
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
from src.pricing.carry_rolldown import carry_rolldown  # noqa: E402
from src.pricing.curve_pricing import (  # noqa: E402
    ZSpreadError,
    curve_clean_price,
    curve_dirty_price,
    z_spread,
)
from src.pricing.daycount import SUPPORTED  # noqa: E402
from src.pricing.key_rate import key_rate_durations, parallel_duration  # noqa: E402

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
px_clean = clean_price(bond, settle, y)
tab_y, tab_c = st.tabs(["Yield-based", "Curve-based"])

with tab_y:
    metrics = {
        "Clean price": f"{px_clean:.4f}",
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
    st.caption("Prices per 100 face. Semi-annual compounding; street convention.")

    st.subheader("Yield-shock table")
    shocks = yield_shock_table(bond, settle, y)
    show = shocks.assign(**{"yield": shocks["yield"] * 100}).rename(
        columns={
            "shock_bps": "Shock bp",
            "yield": "Yield %",
            "full_price": "Dirty px",
            "full_reval_pct": "Full %",
            "duration_pct": "Dur %",
            "dur_convexity_pct": "Dur+Cvx %",
            "duration_err_pct": "Dur err pp",
            "dur_convexity_err_pct": "Dur+Cvx err pp",
        }
    )
    # full width so all 8 columns fit; the frame scrolls horizontally on narrow screens
    st.dataframe(
        show.style.format({"Shock bp": "{:+.0f}", "Yield %": "{:.3f}", "Dirty px": "{:.4f}",
                           "Full %": "{:+.4f}", "Dur %": "{:+.4f}", "Dur+Cvx %": "{:+.4f}",
                           "Dur err pp": "{:+.4f}", "Dur+Cvx err pp": "{:+.5f}"}),
        hide_index=True,
        width="stretch",
    )
    st.caption("Full = full revaluation; errors are approximation minus full, in % points.")

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

with tab_c:
    ac = active_curve()
    if ac is None:
        fit = fit_curve_table(SAMPLE, None, "par", "NSS")
        ac = {"fit": fit, "label": "ILLUSTRATIVE sample", "illustrative": True}
        st.info("No curve selected yet — open the **Yield Curve** page to upload one.")
    if ac["illustrative"]:
        st.warning(ILLUSTRATIVE_MSG)
    curve = ac["fit"].curve
    st.caption(f"Curve: {ac['label']} ({ac['fit'].method}, RMSE {ac['fit'].rmse_bps:.2f} bp).")

    c_clean = curve_clean_price(bond, settle, curve)
    try:
        zs = z_spread(px_clean, bond, settle, curve)
        zs_txt = f"{zs * 1e4:+.1f} bp"
    except ZSpreadError:
        zs_txt = "—"
    m = st.columns(4)
    m[0].metric("Curve clean price", f"{c_clean:.4f}")
    m[1].metric("Curve dirty price", f"{curve_dirty_price(bond, settle, curve):.4f}")
    m[2].metric("Your clean price", f"{px_clean:.4f}")
    m[3].metric("Z-spread", zs_txt)
    st.caption(
        "Z-spread: constant continuously-compounded spread over the curve's zero rates "
        "that reprices your clean price (from the sidebar). Positive = cheap to the curve."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Key-rate durations")
        krd = key_rate_durations(bond, settle, curve)
        kfig = go.Figure(go.Bar(x=[f"{k:g}Y" for k in krd.index], y=krd.values))
        kfig.update_layout(yaxis_title="Duration (years)", height=340, margin={"t": 10})
        st.plotly_chart(kfig, width="stretch")
        st.caption(
            f"Sum {krd.sum():.4f} vs parallel {parallel_duration(bond, settle, curve):.4f}. "
            "1bp triangular bumps on continuous zero rates, full repricing."
        )
    with right:
        st.subheader("12-month carry & roll-down")
        cr = carry_rolldown(bond, settle, curve)
        if cr["matures_in_horizon"]:
            st.info(f"Bond matures {cr['horizon_date']:%d-%b-%Y}, inside the 12-month "
                    "horizon: figures are to maturity and roll-down is zero.")
        tbl = pd.DataFrame(
            {
                "Component": ["Coupon income", "Pull-to-par", "Roll-down", "Price change",
                              "Total"],
                "Per 100 face": [cr["coupon_income"], cr["pull_to_par"], cr["rolldown"],
                                 cr["price_change"], cr["total"]],
                "% of dirty": [cr["coupon_income_pct"], cr["pull_to_par_pct"],
                               cr["rolldown_pct"], cr["price_change_pct"], cr["total_pct"]],
            }
        )
        st.dataframe(tbl.style.format(precision=4), hide_index=True, width="stretch")
        st.caption("Curve unchanged (same rate per tenor); no reinvestment, funding or tax.")
