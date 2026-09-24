"""Refresh CLI.  Usage:  python -m src.ingestion.run_refresh --source fred [--series DGS10 ...]

Each series is processed independently; one failure does not stop the others.
Writes/merges data/metadata/last_updated.json. Exit code 1 if any series failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.ingestion import fred
from src.ingestion import golden_store as gs

META_FILE = fred.ROOT / "data" / "metadata" / "last_updated.json"


def refresh_fred(db: Path, series: list[str], meta_file: Path = META_FILE, fetch=None) -> dict:
    """Refresh ``series`` from FRED into ``db``; returns {series_id: summary|error}."""
    key = fred.load_api_key()
    con = gs.connect(db)
    results: dict[str, dict] = {}
    try:
        for sid in series:
            try:
                kw = {"fetch": fetch} if fetch else {}
                results[sid] = dict(fred.ingest_series(con, sid, key, **kw), status="ok")
            except Exception as e:  # keep going; record the failure
                results[sid] = {"series_id": sid, "status": "error", "error": str(e)}
            print(f"{sid:14s} {results[sid]['status']:5s} "
                  f"{results[sid].get('rows_upserted', results[sid].get('error', ''))}")
    finally:
        con.close()
    write_meta(meta_file, "fred", results)
    return results


def write_meta(meta_file: Path, source: str, results: dict) -> None:
    """Merge results into last_updated.json; failed series keep their previous entry."""
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    block = meta.setdefault(source, {})
    for sid, r in results.items():
        if r["status"] == "ok":
            block[sid] = {k: v for k, v in r.items() if k != "series_id"}
        else:
            block.setdefault(sid, {})["last_error"] = r["error"]
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(meta, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, choices=["fred"])
    p.add_argument("--series", nargs="*", help="subset of series (default: all configured)")
    p.add_argument("--db", type=Path, default=gs.DEFAULT_DB)
    a = p.parse_args(argv)
    series = a.series or list(fred.SERIES)
    try:
        res = refresh_fred(a.db, series)
    except fred.FredError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0 if all(r["status"] == "ok" for r in res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
