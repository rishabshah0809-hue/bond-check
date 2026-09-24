"""FRED ingestion via the official API (api.stlouisfed.org).

Flow per series: fetch series metadata + observations JSON -> save raw bytes untouched
to data/raw/us/{series}/{timestamp}.json -> parse -> validate -> upsert golden store.

Conventions:
- FRED encodes missing observations as the string "." -> stored as value NULL with
  quality_flag MISSING (never filled).
- Values stored exactly as published (units per FRED series metadata); no transform.
- Incremental: observation_start = last stored obs_date - 30 days (revision overlap);
  full history on first load. Overlapping rows are replaced (idempotent upsert).
- obs_date is FRED's "date" (period start for monthly/quarterly series).
- API key: env var FRED_API_KEY, else read from .env in the repo root. Never logged,
  never written to disk by this module (FRED responses do not echo the key).
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from src.ingestion import golden_store as gs
from src.validation import assign_flags, duplicate_dates

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "us"
API = "https://api.stlouisfed.org/fred"
SOURCE = "FRED"
OVERLAP_DAYS = 30
TRANSFORMATION = "none (value as published by FRED; '.' -> NULL/MISSING)"
FRED_LEGAL_URL = "https://fred.stlouisfed.org/legal/"

# series_id -> expected frequency code used by validation (D/W/M/Q)
SERIES: dict[str, str] = {
    "DGS2": "D", "DGS5": "D", "DGS10": "D", "DGS30": "D", "DFF": "D",
    "CPIAUCSL": "M", "PCEPILFE": "M", "UNRATE": "M", "GDPC1": "Q",
    "T10YIE": "D", "VIXCLS": "D", "DCOILBRENTEU": "D", "DTWEXBGS": "D",
}

Fetcher = Callable[[str, dict], bytes]


class FredError(RuntimeError):
    """FRED API returned an error or an unexpected payload."""


def load_api_key(env_file: Path = ROOT / ".env") -> str:
    """FRED_API_KEY from the environment, else from a KEY=VALUE line in ``env_file``."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*FRED_API_KEY\s*=\s*['\"]?([^'\"\s#]+)", line)
            if m:
                key = m.group(1)
    if not key:
        raise FredError("FRED_API_KEY not set (environment or .env). See .env.example.")
    return key


def http_fetch(endpoint: str, params: dict) -> bytes:
    """GET {API}/{endpoint} with ``params``; returns raw response bytes."""
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:  # body carries FRED's error message
        msg = e.read().decode("utf-8", "replace")
        raise FredError(f"FRED HTTP {e.code} for {endpoint}: {msg[:300]}") from None


def save_raw(payload: bytes, series_id: str, kind: str, ts: str, raw_dir: Path = RAW_DIR) -> Path:
    """Write raw bytes untouched to raw_dir/{series}/{ts}[_meta].json."""
    d = raw_dir / series_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / (f"{ts}.json" if kind == "obs" else f"{ts}_{kind}.json")
    p.write_bytes(payload)
    return p


def parse_observations(payload: bytes | dict) -> pd.DataFrame:
    """FRED observations JSON -> DataFrame(obs_date: date, value: float|NaN).

    "." (FRED's missing marker) and any non-numeric value become NaN.
    Raises FredError if the payload has no 'observations' list.
    """
    data = json.loads(payload) if isinstance(payload, bytes | str) else payload
    if "observations" not in data:
        raise FredError(f"unexpected FRED payload: {data.get('error_message', list(data))}")
    obs = data["observations"]
    df = pd.DataFrame(
        {
            "obs_date": pd.to_datetime([o["date"] for o in obs]).date if obs else [],
            "value": pd.to_numeric([o["value"] for o in obs], errors="coerce") if obs else [],
        }
    )
    return df.astype({"value": float})


def parse_series_meta(payload: bytes | dict, series_id: str) -> dict:
    """FRED series JSON -> catalog row (description/unit/frequency from FRED itself)."""
    data = json.loads(payload) if isinstance(payload, bytes | str) else payload
    s = (data.get("seriess") or [{}])[0]
    notes = s.get("notes", "") or ""
    copyright_ = next((x.strip() for x in re.split(r"(?<=\.)\s", notes) if "opyright" in x), "")
    terms = f"{copyright_} " if copyright_ else ""
    terms += f"FRED terms: {FRED_LEGAL_URL}; check series notes before redistribution."
    return {
        "series_id": series_id,
        "description": s.get("title"),
        "unit": s.get("units"),
        "source": SOURCE,
        "frequency": s.get("frequency_short") or SERIES.get(series_id),
        "url": f"https://fred.stlouisfed.org/series/{series_id}",
        "terms_note": terms,
    }


def ingest_series(
    con: duckdb.DuckDBPyConnection,
    series_id: str,
    api_key: str,
    fetch: Fetcher = http_fetch,
    now: datetime | None = None,
    raw_dir: Path = RAW_DIR,
) -> dict:
    """Fetch, store raw, parse, validate and upsert one series. Returns a summary dict."""
    if series_id not in SERIES:
        raise FredError(f"{series_id} not in configured SERIES")
    now = now or datetime.now(UTC).replace(tzinfo=None)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    freq = SERIES[series_id]
    last = gs.last_obs_date(con, series_id)
    start = (last - timedelta(days=OVERLAP_DAYS)) if last else None

    base = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
    meta_raw = fetch("series", base)
    save_raw(meta_raw, series_id, "meta", ts, raw_dir)
    gs.upsert_catalog(con, pd.DataFrame([parse_series_meta(meta_raw, series_id)]))

    params = dict(base, **({"observation_start": start.isoformat()} if start else {}))
    obs_raw = fetch("series/observations", params)
    raw_path = save_raw(obs_raw, series_id, "obs", ts, raw_dir)
    df = parse_observations(obs_raw)

    dups = duplicate_dates(df["obs_date"])
    if dups:
        raise FredError(f"{series_id}: duplicate dates in FRED response: {dups[:5]}")

    rel = raw_path.relative_to(ROOT) if raw_path.is_relative_to(ROOT) else raw_path
    rows = df.assign(
        series_id=series_id,
        source=SOURCE,
        frequency=freq,
        quality_flag="OK",
        retrieved_at=now,
        raw_file_path=str(rel).replace("\\", "/"),
        transformation=TRANSFORMATION,
    )
    n = gs.upsert_observations(con, rows)
    revalidate(con, series_id, freq, now.date())
    return {
        "series_id": series_id,
        "rows_upserted": n,
        "missing_in_batch": int(df["value"].isna().sum()),
        "fetched_from": start.isoformat() if start else None,
        "last_obs_date": str(gs.last_obs_date(con, series_id)),
        "retrieved_at": now.isoformat(timespec="seconds") + "Z",
        "raw_file_path": str(rel).replace("\\", "/"),
    }


def revalidate(con: duckdb.DuckDBPyConnection, series_id: str, freq: str, today: date) -> None:
    """Recompute quality flags over a series' full stored history."""
    hist = gs.read_series(con, series_id)
    if hist.empty:
        return
    flags = assign_flags(hist[["obs_date", "value"]], freq, today)
    gs.set_quality_flags(con, series_id, pd.Series(flags.values, index=hist["obs_date"]))
