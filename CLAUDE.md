# bondcheck — CLAUDE.md

Transparent risk analytics for Indian G-secs/SDLs (spec: docs/PROJECT_SPEC.md).
Shows modelled risk, never buy/sell advice. Built in phases; Phase 1 = scaffold + pricing engine.

## Stack
Python 3.11+, pandas, numpy, scipy, Plotly, Streamlit, pytest, ruff. Config in pyproject.toml.
Later: statsmodels, DuckDB/SQLite, Parquet.

## Layout
- data/raw/{india,us}  raw downloads, untouched
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
- Ask the user before assuming any market convention you are not sure about.
- Do not build modules outside the current phase.

## Commands
- Setup: python -m venv .venv && .venv/Scripts/pip install -e .[dev]
- Tests: .venv/Scripts/python -m pytest -q
- Lint:  .venv/Scripts/ruff check .
- App:   .venv/Scripts/streamlit run app/1_Bond_Calculator.py
