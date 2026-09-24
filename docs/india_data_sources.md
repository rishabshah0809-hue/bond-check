# India data sources — investigation (2026-09-25)

Scope: facts found on official pages/PDFs on the date above. Anything not confirmed from
an official document is marked **UNVERIFIED**. No India site was scraped; no ingestion code
exists. Quotes are short extracts; follow the links for full text.

## Summary table

| Source / data | URL | Free? | Format | History from | Update time | Stable API / link | Login / captcha | Commercial / redistribution |
|---|---|---|---|---|---|---|---|---|
| FBIL G-sec valuation: security prices/YTM, **Par Yield Curve**, **ZCYC**, STRIPS | https://www.fbil.org.in | Live: **paid** from 1-Apr-2022. 7-day-lagged: free, **view only** on FBIL site | UNVERIFIED (site is a JS single-page app; download format not confirmed) | Published since 31-Mar-2018 (Notif. 10/2021) | UNVERIFIED (see FBIL publication-time notice, 09-Feb-2023) | UNVERIFIED — no documented public API | Registration required for licensed use; captcha UNVERIFIED | Paid licence; see quotes F1–F4 |
| FBIL SDL valuation | same | Same as G-sec (priced as one benchmark with G-sec) | UNVERIFIED | 31-Mar-2018 | UNVERIFIED | UNVERIFIED | as above | as above |
| FBIL T-bill curve | same | Paid ("Others" data vendor category) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | as above | Licence required (F1, F4) |
| FBIL USD/INR reference rate | same | Paid from 1-Apr-2019 (F5) | UNVERIFIED | UNVERIFIED (FBIL took over from RBI in 2018) | UNVERIFIED | UNVERIFIED | as above | Licence required |
| CCIL / RBI NDS-OM trades (market watch, individual trades) | https://www.ccilindia.com/web/ccil/rbi-nds-om | Viewable on site; commercial data via paid "Data Services" | Web tables; downloadable files on some pages UNVERIFIED | UNVERIFIED (an Archive section exists) | Intraday / end of day, UNVERIFIED | No public API found; paid feed via CCIL Data Services | Not needed to view; **automated collection prohibited** (C2) | No commercial use without written consent (C1) |
| RBI DBIE: repo rate, LAF/liquidity, 10Y G-sec yield history, CPI mirror | https://data.rbi.org.in/DBIE/ (old dbie.rbi.org.in redirects) | Yes (free) | Excel / CSV / PDF export (per RBI app description) | Varies by series; long 10Y history UNVERIFIED | Daily / weekly / monthly by series | No documented official API (UNVERIFIED) | None found | Research use "with courtesy to DBIE, RBI" (R1; wording from secondary source — **UNVERIFIED**, official disclaimer page returned 404) |
| RBI Handbook of Statistics on Indian Economy (annual) | https://rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+Economy | Yes | Excel/PDF tables (UNVERIFIED which tables) | Decades for key rates (UNVERIFIED exact start) | Annual | Stable per-edition file links (UNVERIFIED) | None | RBI disclaimer covers liability/linking only; no reuse licence text found (R2) |
| dbie.rbihub.in (third-party mirror of DBIE) | https://dbie.rbihub.in/docs | Yes, JSON API | JSON | as DBIE | Mirror of last scrape, "not a live feed" | Yes (data-api.dbie.rbihub.in) | No key per docs | Official status **UNVERIFIED**; it is a scrape of DBIE → do **not** use as primary |
| MoSPI: CPI (all-India, base 2012 → new base UNVERIFIED), GDP (NAS) | https://www.mospi.gov.in ; eSankhyiki portal; API base api.mospi.gov.in (UNVERIFIED) | Yes | JSON API / Excel | CPI 2011 onward (base 2012); GDP series by base year — UNVERIFIED | Monthly CPI (12th of month) / quarterly GDP — UNVERIFIED | Official API exists (per MoSPI's own GitHub `nso-india`); key requirement UNVERIFIED | None found | GODL-India applies to govt data (per data.gov.in); MoSPI site copyright: reproduce free "after taking proper permission" (M1, secondary source — UNVERIFIED) |

## Terms quoted (with links)

- **F1** FBIL FAQ (2023) — "The Benchmarks published by FBIL are its sole property and accordingly any use of its Benchmarks including commercial use and distribution/ display will be only with the express authorization of FBIL." https://www.fbil.org.in/uploads/FAQ_s_updates_30th_Nov_2023_edited_version_1def7b65bb.pdf
- **F2** Same FAQ, End-User licence needed and "usage is fee liable" for purposes incl. "(a) Valuation of portfolio and assets … (e) Pricing Curves". Delayed data used for these purposes is also fee liable (FAQ III.5).
- **F3** FBIL Notification No. 10 (28-Dec-2021) — "It has been decided to make the G-sec and SDL valuation benchmarks live data fee- liable with effect from April 1, 2022." and "the 7 day (168 hours) lag data will be available free of cost to the members of the public only for viewing on the FBIL website". Fees p.a.: End users for valuation ₹50,000; other purposes ₹2,50,000; co-op/SFB/RRB ₹25,000; data vendors ₹1,50,000/month. https://www.fbil.org.in/uploads/Pricing_of_FBIL_G_Sec_Valuation_and_SDL_Valuation_benchmarks_c4832dcaaa.pdf
- **F4** FBIL Data Fee FAQ (2018) Q.7 — "If you choose to publish or redistribute FBIL benchmarks, either real time or delayed, through your web portal or any other means, redistribution fee will be applicable." https://www.fbil.org.in/uploads/Data_Fee_Schedule_FAQ_repl_3576a15203_f39da07c83.pdf (its Q.14 "free of charge" statement for G-sec/SDL is **superseded** by F3.)
- **F5** Same (2018) Q.13 — "the FBIL Reference Rate is fee liable with effect from April 01, 2019."
- **F6** Educational institutes: ₹10,000 per benchmark p.a. (FAQ 2023, III.4).
- **C1** CCIL Terms of Use 4.1 — user shall not "copy/publish/distribute or otherwise disseminates any Content available on the Website for any commercial uses, except with the express written consent of CCIL." https://www.ccilindia.com/documents/d/ccil/terms-of-use
- **C2** CCIL Terms 4.8 — "The User shall not conduct any systematic or automated data collection activities which include but are not limited to scrapping, data mining, data extraction and data harvesting"; 5.2 content not offered for download "shall not be copied, web-scraped …".
- **R1** DBIE — users "can use the data for their research work with courtesy to the Database on Indian Economy, Reserve Bank of India" (seen via search snippet of RBI's DBIE pages; official disclaimer URL https://data.rbi.org.in/DBIE/doc/disclaimer.html returned 404 → **UNVERIFIED**).
- **R2** RBI website disclaimer — covers accuracy/liability and linking ("Internal page linking requires prior written permission"); no explicit data reuse licence found. https://www.rbi.org.in/Scripts/Disclaimer.aspx
- **M1** MoSPI copyright policy — material "may be reproduced free of charge after taking proper permission" by email (search snippet; page body did not render → **UNVERIFIED**). https://www.mospi.gov.in/copyright-policy

## Recommendations

**(a) Cheapest legitimate daily par/zero curve.**
- For the product as specified (valuing portfolios, "pricing curves") FBIL's own terms make use fee-liable even with lagged data (F2, FBIL FAQ III.5). Cheapest licensed route: FBIL End-User "For Valuation" ₹50,000 p.a. (co-op banks ₹25,000); redistribution to users of a web app is likely a vendor/redistribution licence (₹1.5 lakh/month) — **needs FBIL's written answer**.
- Licence-free alternative: **build our own curve** from RBI-published data (DBIE/weekly statistical supplement G-sec yields by maturity, T-bill auction cut-offs) and fit NSS ourselves. Lower quality/frequency, but official and free to use with attribution (subject to R1 being confirmed).
- Per-user option: users who hold their own FBIL licence upload FBIL files themselves (CSV fallback below) — we never redistribute.

**(b) 2008–2018 history** (pre-FBIL valuation, which starts 31-Mar-2018):
- RBI DBIE / Handbook of Statistics: G-sec yields by tenor/10Y benchmark, T-bill yields, repo — primary candidate (coverage per tenor UNVERIFIED).
- FIMMDA published the pre-2018 valuation curve; availability and terms **UNVERIFIED** (FBIL FAQ says FIMMDA data is member-view-only).
- CCIL archives: viewing only; automated collection prohibited (C2) — use only via a paid CCIL data-services agreement.

**(c) Manual CSV upload fallback** (user-supplied, stored with source = "USER_UPLOAD" and file lineage):
- Daily par/zero curve (tenor_years, yield_pct, curve_date, rate_type) — FBIL or other licensed source.
- Security master (ISIN, coupon, maturity, issuer) — until an official machine-readable list is confirmed.
- SDL valuations and USD/INR reference rate (FBIL-licensed users only).
- Holdings (already planned in Module 5).
