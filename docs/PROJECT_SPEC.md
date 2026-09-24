# Project Spec: Indian Fixed-Income Risk & Analytics Platform

## 1. What we're building
A web-based risk and analytics tool for Indian government (G-sec) and state (SDL) bonds. It shows how much bond holdings could gain or lose when interest rates, inflation, oil, the rupee, or US yields move, and which bonds and factors drive that risk.

Positioning: "Affordable, transparent fixed-income risk analytics for India's mid-tier and advised investors." Not "AI predicts bond prices"; not a free Aladdin/Bloomberg clone.

Core principle: every number is traceable to an official source, every model is backtested, and the tool shows modelled risk rather than buy/sell advice.

## 2. Users
| Segment | Problem | Priority |
|---|---|---|
| IFAs and wealth advisers | Need clear, explainable interest-rate risk reports for clients | Primary |
| Co-op bank, small NBFC, corporate treasuries | Manage G-sec books in Excel; no affordable risk tools | Primary |
| Family offices, small PMS/AIF debt managers | Want portfolio VaR and stress testing without a Bloomberg seat | Secondary |
| Retail holders of long G-secs (RBI Retail Direct) | Don't realise how much long bond prices can swing | Secondary (education) |
| Finance students, CFA/FRM candidates | Want hands-on fixed-income tools | Community |

Large banks, AMCs and insurers are out of scope for now.

## 3. Problems solved
- Scattered data across RBI, FBIL, CCIL, NSE, MoSPI — consolidate and clean.
- No affordable risk analytics ("What if yields rise 100 bps?", "What would the 2013 taper tantrum do today?").
- Poor risk communication — clear visual explanations of duration, curve risk and tail loss.

## 4. Modules
### Module 1: Market
- End-of-day Indian yield curve 3M–40Y
- Nelson-Siegel-Svensson fit (level, slope, curvature)
- Curve history and comparisons (today vs 1M vs 1Y ago)
- Spreads: 2s10s, 5s10s, India–US 10Y, SDL over G-sec
- Macro dashboard: India CPI, GDP growth, repo, liquidity, USD/INR, crude; US CPI, Fed Funds, US 2Y/10Y, VIX

### Module 2: Bond analytics (any G-sec/SDL by ISIN)
- Clean price, dirty price, accrued interest; YTM
- Macaulay and modified duration, convexity, DV01
- Key-rate durations (1Y, 2Y, 5Y, 10Y, 15Y, 30Y)
- Carry and roll-down (12-month expected return if yields don't move)
- Full cash-flow schedule
- Yield-shock table (−100 to +100 bps): duration approx vs duration+convexity vs full revaluation

### Module 3: Scenario lab
- Custom shocks: parallel, steepener, flattener, butterfly; macro shocks (CPI +1%, repo +50 bps, US 10Y +30 bps, crude +15%)
- Historical replay: GFC (Sep–Dec 2008), Taper tantrum (May–Aug 2013), Demonetisation (Nov 2016), 2018 yield spike + IL&FS, COVID (Feb–Apr 2020), 2022 inflation/rate cycle (Apr–Dec 2022)
- Reverse stress test (later)

### Module 4: Risk engine
- Historical, parametric and Monte Carlo VaR (10k–50k curve paths)
- Expected Shortfall 95%/99%
- Risk decomposition by curve segment and bond
- Always labelled "simulated 5th percentile", never a prediction

### Module 5: Portfolio
- Enter/upload holdings (CSV: ISIN, face value, purchase price)
- Value, duration, DV01, yield, key-rate profile; scenarios and VaR on whole portfolio
- Concentration by maturity bucket and issuer
- Downloadable PDF risk report

### Module 6: Transparency
- Data lineage for every number
- Data quality centre: missing/stale data shown as "—", never invented
- Model cards; backtest page (VaR breaches, MAE/RMSE, walk-forward)

### Later
Macro regime detector, corporate credit risk, liquidity haircuts, P&L attribution, optimiser, ALM, alerts, AI explainer (no number generation).

## 5. Data sources (all free)
India: FBIL (G-sec par curve, SDL valuations, T-bills, USD/INR reference), CCIL/RBI NDS-OM (trades), RBI/CCIL issuance lists (security master), RBI DBIE (repo, liquidity, money supply, long 10Y history), MoSPI/RBI DBIE (CPI, GDP growth).
US (FRED): DGS2/5/10/30, DFF, FEDFUNDS, CPIAUCSL, PCEPILFE, UNRATE, GDPC1, T10YIE, VIXCLS, DCOILBRENTEU, DTWEXBGS.

Data rules: official sources primary; Investing.com/Moneycontrol only for manual cross-checks, never scraped. Store raw downloads untouched, then clean into processed files. Check FBIL/NSE/CCIL terms before commercial redistribution.

## 6. Architecture
Official sources → ingestion (scheduled) → validation (missing/stale/outlier) → golden DB (value, date, source, frequency, quality flag) → curve / pricing / macro engines → risk engine → portfolio aggregation → Streamlit UI + PDF reports.

Stack: Python, pandas, NumPy, SciPy, statsmodels, Plotly, Streamlit, SQLite/DuckDB, Parquet. GitHub Actions for daily refresh.

```
data/
  raw/india/  raw/us/
  processed/  (curves_daily.parquet, macro_monthly.parquet, securities.parquet)
  metadata/   (sources.json, last_updated.json)
src/
  ingestion/  validation/  curves/  pricing/  risk/  scenarios/  portfolio/  reports/
tests/        (pricing verified against FBIL/CCIL published valuations)
app/          (Streamlit pages)
docs/         (model cards, methodology)
```

## 7. Modelling approach
- Pricing: full cash-flow valuation with Indian G-sec conventions (semi-annual, 30/360, correct accrued). Validate against FBIL to within a few paise.
- Curve: daily NSS fit; model level/slope/curvature factors.
- Monte Carlo: simulate curve factors (bootstrap or macro VAR), rebuild curve, reprice, aggregate.
- Frequency: daily for market risk; monthly for macro-to-yield model.
- Validation: walk-forward only, VaR breach tests, coefficient stability.
