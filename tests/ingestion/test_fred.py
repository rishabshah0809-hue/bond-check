"""FRED ingestion + golden store tests. Fixtures only (ILLUSTRATIVE); no network."""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from src.ingestion import fred
from src.ingestion import golden_store as gs
from src.ingestion.run_refresh import write_meta

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "fred"
NOW = datetime(2026, 1, 14, 18, 0, 0)


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeFred:
    """Replays fixture files and records request params."""

    def __init__(self, obs_file: str):
        self.obs_file = obs_file
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, endpoint: str, params: dict) -> bytes:
        self.calls.append((endpoint, params))
        return fixture("DGS10_meta.json" if endpoint == "series" else self.obs_file)


@pytest.fixture
def con(tmp_path):
    c = gs.connect(tmp_path / "golden.duckdb")
    yield c
    c.close()


# ---------- parsing ----------
def test_parse_dot_is_missing_not_filled():
    df = fred.parse_observations(fixture("DGS10_initial.json"))
    assert len(df) == 7
    assert df["obs_date"].iloc[0] == date(2026, 1, 1)
    assert df["value"].isna().sum() == 1
    assert pd.isna(df.set_index("obs_date").loc[date(2026, 1, 2), "value"])
    assert df["value"].iloc[0] == pytest.approx(4.10)


def test_parse_error_payload_raises():
    with pytest.raises(fred.FredError, match="not registered"):
        fred.parse_observations(fixture("error.json"))


def test_parse_series_meta_uses_fred_metadata():
    row = fred.parse_series_meta(fixture("DGS10_meta.json"), "DGS10")
    assert row["unit"] == "Percent" and row["frequency"] == "D"
    assert "Copyright, 2026, Example Owner." in row["terms_note"]
    assert row["url"] == "https://fred.stlouisfed.org/series/DGS10"


def test_api_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comment\nFRED_API_KEY = 'abc123'\n")
    assert fred.load_api_key(env) == "abc123"
    with pytest.raises(fred.FredError):
        fred.load_api_key(tmp_path / "none.env")


# ---------- ingest / store ----------
def test_ingest_saves_raw_untouched_and_loads(con, tmp_path):
    fake = FakeFred("DGS10_initial.json")
    res = fred.ingest_series(con, "DGS10", "KEY", fetch=fake, now=NOW, raw_dir=tmp_path / "raw")
    raw = tmp_path / "raw" / "DGS10" / "20260114T180000Z.json"
    assert raw.read_bytes() == fixture("DGS10_initial.json")
    assert res["rows_upserted"] == 7 and res["missing_in_batch"] == 1
    assert "observation_start" not in fake.calls[1][1]  # first load = full history
    rows = gs.read_series(con, "DGS10")
    assert len(rows) == 7
    missing = rows[rows["value"].isna()]
    assert list(missing["quality_flag"]) == ["MISSING"]
    assert (rows["source"] == "FRED").all() and rows["transformation"].str.startswith("none").all()
    cat = con.execute("SELECT unit FROM series_catalog WHERE series_id='DGS10'").fetchone()
    assert cat == ("Percent",)


def test_upsert_is_idempotent(con, tmp_path):
    fake = FakeFred("DGS10_initial.json")
    for _ in range(3):
        fred.ingest_series(con, "DGS10", "KEY", fetch=fake, now=NOW, raw_dir=tmp_path)
    assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == 7
    assert con.execute("SELECT count(*) FROM series_catalog").fetchone()[0] == 1


def test_upsert_rejects_duplicate_keys(con):
    row = {c: None for c in gs.OBS_COLUMNS} | {
        "series_id": "X", "obs_date": date(2026, 1, 1), "value": 1.0, "source": "T",
        "frequency": "D", "quality_flag": "OK", "retrieved_at": NOW,
    }
    with pytest.raises(ValueError, match="duplicate"):
        gs.upsert_observations(con, pd.DataFrame([row, row]))


def test_incremental_fetch_uses_30_day_overlap_and_applies_revisions(con, tmp_path):
    fred.ingest_series(con, "DGS10", "KEY", fetch=FakeFred("DGS10_initial.json"),
                       now=NOW, raw_dir=tmp_path)
    fake = FakeFred("DGS10_incremental.json")
    res = fred.ingest_series(con, "DGS10", "KEY", fetch=fake, now=NOW, raw_dir=tmp_path)
    assert fake.calls[1][1]["observation_start"] == "2025-12-10"  # 2026-01-09 - 30d
    assert res["fetched_from"] == "2025-12-10"
    rows = gs.read_series(con, "DGS10").set_index("obs_date")
    assert len(rows) == 9
    assert rows.loc[pd.Timestamp("2026-01-09"), "value"] == pytest.approx(4.15)  # revised


def test_unknown_series_rejected(con):
    with pytest.raises(fred.FredError):
        fred.ingest_series(con, "NOTASERIES", "KEY", fetch=FakeFred("DGS10_initial.json"))


def test_write_meta_merges_and_keeps_previous_on_error(tmp_path):
    meta = tmp_path / "last_updated.json"
    write_meta(meta, "fred", {"DGS10": {"series_id": "DGS10", "status": "ok",
                                        "last_obs_date": "2026-01-09"}})
    write_meta(meta, "fred", {"DGS10": {"series_id": "DGS10", "status": "error",
                                        "error": "boom"}})
    d = json.loads(meta.read_text())["fred"]["DGS10"]
    assert d["last_obs_date"] == "2026-01-09" and d["last_error"] == "boom"
