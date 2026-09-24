"""Data Quality — one row per series in the golden store: freshness, flags, source."""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ingestion.golden_store import DEFAULT_DB, connect  # noqa: E402
from src.validation import STALE_AFTER_DAYS, staleness  # noqa: E402

st.set_page_config(page_title="Data Quality", layout="wide")
st.title("Data Quality")
st.caption(
    "Missing values are never filled; they show as “—”. Flags: OK, STALE (latest point "
    f"older than {STALE_AFTER_DAYS} days by frequency), OUTLIER (robust z-score of change), "
    "MISSING (source published no value)."
)

EMPTY_MSG = (
    "No data in the golden store yet. Add your FRED key to `.env` (see `.env.example`), "
    "then run `python -m src.ingestion.run_refresh --source fred`."
)

if not DEFAULT_DB.exists():
    st.info(EMPTY_MSG)
    st.stop()

con = connect(DEFAULT_DB, read_only=True)
summary = con.execute(
    """
    SELECT o.series_id, c.description, c.unit, o.source,
           any_value(o.frequency) AS frequency,
           max(o.obs_date) FILTER (WHERE o.value IS NOT NULL) AS last_valid_date,
           count(*) AS rows,
           count(*) FILTER (WHERE quality_flag = 'OK') AS ok,
           count(*) FILTER (WHERE quality_flag = 'STALE') AS stale,
           count(*) FILTER (WHERE quality_flag = 'OUTLIER') AS outlier,
           count(*) FILTER (WHERE quality_flag = 'MISSING') AS missing,
           max(o.retrieved_at) AS retrieved_at,
           c.url, c.terms_note
    FROM observations o JOIN series_catalog c USING (series_id)
    WHERE c.public_display_ok
    GROUP BY o.series_id, c.description, c.unit, o.source, c.url, c.terms_note
    ORDER BY o.source, o.series_id
    """
).df()
hidden = con.execute(
    "SELECT count(*) FROM series_catalog WHERE NOT public_display_ok"
).fetchone()[0]
con.close()

if hidden:
    st.info(
        f"{hidden} series hidden until their licence terms are reviewed "
        "(approve with `python -m src.ingestion.catalog --approve <SERIES>`)."
    )

if summary.empty:
    if not hidden:
        st.info(EMPTY_MSG)
    st.stop()

today = date.today()
ages = [
    staleness(None if pd.isna(d) else d, f, today)
    for d, f in zip(summary["last_valid_date"], summary["frequency"], strict=True)
]
summary.insert(6, "age_days", [a for a, _ in ages])
summary.insert(7, "status", ["STALE" if s else "fresh" for _, s in ages])

c1, c2, c3 = st.columns(3)
c1.metric("Series", len(summary))
c2.metric("Stale series", int(sum(s for _, s in ages)))
c3.metric("Outlier flags", int(summary["outlier"].sum()))

st.dataframe(
    summary.astype(object).where(summary.notna(), "—"),
    hide_index=True,
    width="stretch",
    column_config={"url": st.column_config.LinkColumn("source URL")},
)

meta_file = ROOT / "data" / "metadata" / "last_updated.json"
if meta_file.exists():
    meta = json.loads(meta_file.read_text())
    errors = {
        f"{src}:{sid}": v["last_error"]
        for src, block in meta.items()
        for sid, v in block.items()
        if "last_error" in v
    }
    if errors:
        st.subheader("Last refresh errors")
        st.json(errors)
