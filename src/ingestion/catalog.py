"""Catalog admin CLI: record which series may be shown to users.

    python -m src.ingestion.catalog --list
    python -m src.ingestion.catalog --approve DGS10 DGS2     # after checking their terms
    python -m src.ingestion.catalog --revoke VIXCLS
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.ingestion import golden_store as gs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--approve", nargs="+", metavar="SERIES")
    g.add_argument("--revoke", nargs="+", metavar="SERIES")
    p.add_argument("--db", type=Path, default=gs.DEFAULT_DB)
    a = p.parse_args(argv)
    con = gs.connect(a.db)
    try:
        if a.list:
            rows = con.execute(
                "SELECT series_id, public_display_ok, terms_note FROM series_catalog ORDER BY 1"
            ).fetchall()
            for sid, ok, note in rows:
                print(f"{sid:14s} {'YES' if ok else 'no ':3s}  {(note or '')[:90]}")
            return 0
        ids, ok = (a.approve, True) if a.approve else (a.revoke, False)
        if ok:
            for sid, note in con.execute(
                "SELECT series_id, terms_note FROM series_catalog WHERE series_id IN "
                f"({','.join('?' * len(ids))})", ids
            ).fetchall():
                if note and "opyright" in note:
                    print(f"warning: {sid} notes a third-party copyright: {note[:120]}")
        n = gs.set_public_display(con, ids, ok)
        print(f"updated {n} of {len(ids)} series")
        return 0 if n == len(ids) else 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
