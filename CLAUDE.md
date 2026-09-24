# bondcheck — CLAUDE.md

Transparent risk analytics for Indian G-secs/SDLs (spec: docs/PROJECT_SPEC.md).
Shows modelled risk, never buy/sell advice. Phases: 1 pricing (done); 2 data layer: DuckDB golden store, FRED, validation (done);
3 curve engine (partly pre-built in src/curves, src/pricing/curve_risk.py).

## Stack
Python 3.11+, pandas, numpy, scipy, Plotly, Streamlit, pytest, ruff. Config in pyproject.toml.
Later: statsmodels, DuckDB/SQLite, Parquet.

## Layout
- data/raw/{india,us}  raw downloads, untouched
- data/golden.duckdb   golden store (observations, series_catalog); not committed
- data/processed/      cleaned parquet; data/metadata/ sources + last_updated
- src/{ingestion,validation,curves,pricing,risk,scenarios,portfolio,reports}
- tests/               mirrors src/ (tests/pricing/ ...)
- app/                 Streamlit pages (N_Name.py)
- docs/                spec, model cards, methodology

## Rules
- Never invent market data. Missing data = None/NaN, displayed as "—".
- Sample bonds/yields in tests or demos must be labelled "ILLUSTRATIVE".
- Every model function has a docstring stating conventions and assumptions.
- Every pricing function has pytest tests. Run tests after each change.
- No scraping of non-official sites. No network calls in tests.
- Data fetch (when built): FRED API only; Indian data from files placed manually in data/raw.
- Ask the user before assuming any market convention you are not sure about.
- Do not build modules outside the current phase.

## Commands
- Setup: python -m venv .venv && .venv/Scripts/pip install -e .[dev]
- Tests: .venv/Scripts/python -m pytest -q
- Lint:  .venv/Scripts/ruff check .
- App:   .venv/Scripts/streamlit run app/1_Bond_Calculator.py  (extra pages in app/pages/)
- Refresh: .venv/Scripts/python -m src.ingestion.run_refresh --source fred  (needs .env)
