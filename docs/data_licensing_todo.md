# Data licensing — questions to send

Context to include in each email (edit as needed):
> We are building a web-based (SaaS) risk-analytics tool for Indian G-secs/SDLs aimed at
> IFAs, co-operative banks, small NBFC treasuries and family offices. It computes
> modelled risk (duration, key-rate duration, stress scenarios, VaR); it does not give
> buy/sell advice. We want to use your data correctly and would like to confirm the terms.

Background for us: see docs/india_data_sources.md (quotes F1–F6, C1–C2, R1–R2, M1).

## FBIL (fbil@fbil.org.in, operations@fbil.org.in)

1. Our users would upload FBIL par-yield / ZCYC / valuation files that **they** licensed
   from FBIL, and our software would fit a curve and value **their own** holdings. Is that
   covered by each user's End-User licence, or does our platform also need a licence?
2. If we host the curves centrally, which licence applies: End-User "for valuation"
   (₹50,000 p.a.), "other purposes" (₹2,50,000 p.a.), or Market Data Vendor
   (₹1,50,000 per month)? Are the Notification No. 10 (28-Dec-2021) fees still current?
3. Does showing **derived** numbers only (our fitted curve, bond prices, durations, VaR)
   — never FBIL's raw published rates — count as "redistribution/display"?
4. Is the 7-day-lagged data (free "only for viewing") usable for back-testing or
   historical scenario replay inside our tool, or is that also fee-liable?
5. Is there a start-up / low-turnover / pilot tier, or a free evaluation period?
6. Is there a machine-readable download (CSV/API) for licensed users, and at what time
   are the G-sec/SDL valuation and par/ZCYC curves published each business day?
7. How far back does FBIL history go (valuation curves start 31-Mar-2018?) and can it be
   licensed as a one-off historical file?
8. What attribution wording must appear next to FBIL-derived output?

## RBI (DBIE / DSIM)

1. May DBIE data (G-sec yields by tenor, T-bill yields, repo rate, LAF/liquidity, CPI) be
   used in a commercial SaaS tool with attribution "Source: Database on Indian Economy,
   RBI"? What exact attribution wording do you require?
2. The DBIE disclaimer page (https://data.rbi.org.in/DBIE/doc/disclaimer.html) returns
   404 — where are the current terms of use published?
3. Is there an official API or stable bulk-download URL for DBIE series, and is
   automated (scheduled) downloading permitted? Any rate limits?
4. Which series give daily G-sec yields by tenor (1Y–30Y) back to 2008, and at what
   frequency? Are these market yields, FIMMDA/FBIL valuation yields, or computed by RBI?
5. Are users allowed to display charts/tables derived from DBIE data to their clients?

## MoSPI (eSankhyiki / NSO)

1. Is MoSPI data from the eSankhyiki API (api.mospi.gov.in) covered by the Government
   Open Data License – India (GODL), including commercial use with attribution?
2. The website copyright policy says material may be reproduced "after taking proper
   permission" — does that apply to API data, and how do we request permission?
3. Does the API require a key? Any rate limits or terms for scheduled downloads?
4. For CPI (all-India, combined) and quarterly GDP growth: which endpoints/series ids,
   and how are base-year revisions and back-series published?
5. Required attribution wording.

## Also check (not India)

- FRED: VIXCLS carries "Copyright, 2016, Chicago Board Options Exchange, Inc." — check
  Cboe terms before showing VIX to users. Review FRED legal page
  (https://fred.stlouisfed.org/legal/) for the other 12 series, then approve with
  `python -m src.ingestion.catalog --approve <SERIES>`.
