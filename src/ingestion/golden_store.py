"""Golden store: a DuckDB file holding every observation with its lineage.

Tables
- observations(series_id, obs_date, value, source, frequency, quality_flag,
  retrieved_at, raw_file_path, transformation), primary key (series_id, obs_date).
  ``value`` is NULL when the source published the date as missing; it is never filled.
- series_catalog(series_id, description, unit, source, frequency, url, terms_note).

Upserts are idempotent: re-loading the same rows replaces them in place (INSERT OR
REPLACE on the primary key), so row counts never grow from repeated loads.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "golden.duckdb"

OBS_COLUMNS = [
    "series_id", "obs_date", "value", "source", "frequency", "quality_flag",
    "retrieved_at", "raw_file_path", "transformation",
]
CATALOG_COLUMNS = ["series_id", "description", "unit", "source", "frequency", "url", "terms_note"]

_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    series_id      VARCHAR NOT NULL,
    obs_date       DATE NOT NULL,
    value          DOUBLE,
    source         VARCHAR NOT NULL,
    frequency      VARCHAR NOT NULL,
    quality_flag   VARCHAR NOT NULL,
    retrieved_at   TIMESTAMP NOT NULL,
    raw_file_path  VARCHAR,
    transformation VARCHAR,
    PRIMARY KEY (series_id, obs_date)
);
CREATE TABLE IF NOT EXISTS series_catalog (
    series_id   VARCHAR PRIMARY KEY,
    description VARCHAR,
    unit        VARCHAR,
    source      VARCHAR,
    frequency   VARCHAR,
    url         VARCHAR,
    terms_note  VARCHAR
);
"""


def connect(path: str | Path = DEFAULT_DB, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the golden store and ensure tables exist."""
    path = Path(path)
    if read_only:
        return duckdb.connect(str(path), read_only=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(_DDL)
    return con


def upsert_observations(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Insert or replace rows keyed on (series_id, obs_date). Returns rows written.

    Raises ValueError if ``df`` has duplicate keys (validate before loading).
    """
    if df.empty:
        return 0
    if df.duplicated(["series_id", "obs_date"]).any():
        raise ValueError("duplicate (series_id, obs_date) rows in upsert batch")
    batch = df[OBS_COLUMNS]  # noqa: F841 - referenced by DuckDB replacement scan
    con.execute(f"INSERT OR REPLACE INTO observations SELECT {', '.join(OBS_COLUMNS)} FROM batch")
    return len(df)


def upsert_catalog(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    """Insert or replace series_catalog rows keyed on series_id."""
    cat = df[CATALOG_COLUMNS]  # noqa: F841
    cols = ", ".join(CATALOG_COLUMNS)
    con.execute(f"INSERT OR REPLACE INTO series_catalog SELECT {cols} FROM cat")


def last_obs_date(con: duckdb.DuckDBPyConnection, series_id: str):
    """Latest stored obs_date for a series (including NULL-valued rows), or None."""
    return con.execute(
        "SELECT max(obs_date) FROM observations WHERE series_id = ?", [series_id]
    ).fetchone()[0]


def read_series(con: duckdb.DuckDBPyConnection, series_id: str) -> pd.DataFrame:
    """All stored rows for a series, ordered by date."""
    return con.execute(
        "SELECT * FROM observations WHERE series_id = ? ORDER BY obs_date", [series_id]
    ).df()


def set_quality_flags(con: duckdb.DuckDBPyConnection, series_id: str, flags: pd.Series) -> None:
    """Overwrite quality_flag for ``series_id``; ``flags`` is indexed by obs_date."""
    upd = pd.DataFrame({"obs_date": pd.to_datetime(flags.index).date, "flag": flags.values})  # noqa: F841
    con.execute(
        """UPDATE observations SET quality_flag = upd.flag FROM upd
           WHERE observations.series_id = ? AND observations.obs_date = upd.obs_date""",
        [series_id],
    )
