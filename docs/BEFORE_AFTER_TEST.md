# Before / after test: time to a trustworthy answer

**Purpose.** Measure, not claim, how much faster the governed tool answers the questions an acquisitions
team actually asks, and whether the answers agree.

**Rules**
1. *Before* = Microsoft Excel (or Google Sheets) on the raw CSV exports in `data/sales/` and `data/rents/` (unzipped)
   , starting from a freshly opened file. No macros prepared in advance.
2. *After* = the live app or `sql/analysis_queries.sql`.
3. Start the timer when the file/app is open; stop when the answer is written down.
4. Write down the **answer** as well as the time. If the Excel answer differs from the tool's, note why
   (e.g. mortgages counted as sales). A fast wrong answer is not a win.
5. Record only what was actually measured. Leave a cell blank rather than estimate.

| # | Question | Excel: time | Excel: answer | Tool: time | Tool: answer | Same answer? Why not? |
|---|---|---|---|---|---|---|
| 1 | How many real residential sales were there in Business Bay in Aug–Oct 2026, and what was the median price per sqm? | | | SQL 10 ms | 995 sales; AED 22,335 per sqm | |
| 2 | Top 5 areas for apartments with a median ready price under AED 1M, ranked by ready resale sales per month | | | SQL <1 ms | JVC (337.8/mo), Arjan (88.8), International City Ph 1 (88.5), Dubai Sports City (73.5), Discovery Gardens (64.5) | |
| 3 | Gross rental yield for apartments in Jumeirah Village Circle | | | SQL <1 ms; AI assistant under 20 s | 7.2%, Reliable (2,027 ready sales, 20,764 rent contracts) | |
| 4 | Which areas have an apartment yield above 7% with a *Reliable* sample? | | | SQL <1 ms | 13 areas, led by Me'aisem First (9.0%) and Al Warsan First (8.9%) | |
| 5 | Was the off-plan premium per sqm different in May–Jul vs Aug–Oct 2026? | | | SQL 40 ms | 20.6% vs 20.8%: no real change | |
| 6 | Refresh: a new month's export arrives. Time to updated, checked KPIs | | n/a | 10 s for the full rebuild and 23 checks (plus the manual DLD download) | 0 FAIL, 13 WARN, 10 PASS | |

**Tool side: measured 15 Nov 2026.** Times are machine times: SQL execution against the built database, the
pipeline's own "Done in N s", and the AI assistant's response time observed on the live app. They do not include a
person choosing filters or typing the question.

**Excel side: not measured yet.** It has to be timed by a person working in Excel from the raw exports; a script
would not be a fair comparison. Questions 1 and 3 are enough for a headline number (about 30 to 45 minutes).

Hints for the Excel side (these are exactly the traps the pipeline handles): Q3 needs rents and sales joined, but
the rent file calls JVC "Al Barsha South Fourth"; rent rows contain exact duplicates; the sales file contains
mortgages, gifts, land and offices.

  **Date:** ______  **Excel version:** ______

Pipeline refresh time is printed by `python -m pipeline.build` ("Done in N s") on the machine running it.
