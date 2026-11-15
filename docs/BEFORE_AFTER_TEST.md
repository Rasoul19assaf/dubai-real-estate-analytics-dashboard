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

| # | Question | Excel:| # | Question | Excel: time | Excel: answer | Tool: time | Tool: answer | Same answer? Why not? |
|---|---|---|---|---|---|---|
| 1 | How many real residential sales were there in Business Bay in Aug–Oct 2026, and what was the median price per sqm? | | | | | |
| 2 | Top 5 areas for apartments with a median ready price under AED 1M, ranked by ready resale sales per month | | | | | |
| 3 | Gross rental yield for apartments in Jumeirah Village Circle | | | | | |
| 4 | Which areas have an apartment yield above 7% with a *Reliable* sample? | | | | | |
| 5 | Was the off-plan premium per sqm different in May–Jul vs Aug–Oct 2026? | | | | | |
| 6 | Refresh: a new month's export arrives. Time to updated, checked KPIs | | | | | |

Hints for the Excel side (these are exactly the traps the pipeline handles): Q3 needs rents and sales joined, but
the rent file calls JVC "Al Barsha South Fourth"; rent rows contain exact duplicates; the sales file contains
mortgages, gifts, land and offices.

  **Date:** ______  **Excel version:** ______

Pipeline refresh time is printed by `python -m pipeline.build` ("Done in N s") on the machine running it.
