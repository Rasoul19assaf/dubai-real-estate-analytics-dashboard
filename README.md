# Dubai Property Acquisition Screening & Data Operations

**From "a dashboard" to a governed data process.** One source of truth for Dubai Land Department (DLD)
sales and Ejari rent data, KPIs with written definitions and owners, and data-quality checks that flag
problems on every refresh, feeding an acquisition-screening tool that answers
*where to buy, what gross yield to expect, and how liquid each area is.*

**Live demo:** https://dubai-real-estate-analytics-dashboar-ymaht7zn7wxfy6zkgttty9.streamlit.app/
**Data:** 101,884 DLD transactions and 277,351 Ejari rent contracts, May–October 2026, exported from
[dubailand.gov.ae](https://dubailand.gov.ae/en/open-data/real-estate-data).

---

## Case study

### 1. Problem
A property-investment team screening Dubai acquisitions needs three numbers per area and unit type:
**price**, **rental yield** and **liquidity**. DLD publishes everything needed, but not in a form anyone
can trust as delivered:

- **Sales and rents don't share area names.** Sales use community names ("Jumeirah Village Circle"); Ejari
  rents use DLD land areas ("Al Barsha South Fourth"). Joined on name, only **43%** of sales find matching rents.
- **The "Residential" filter doesn't hold.** The Usage column is blank on all 101,884 rows, and 8,018 sales of
  land, offices and shops come through anyway.
- **Rows are not records.** 9.3% of rent rows (25,805) are exact duplicates, and the rent export has no contract
  number to catch them. In sales, 149 portfolio mortgages repeat the full portfolio amount on every unit,
  **AED 8.1B** that never changed hands if you sum the column.
- **Sales are mixed with everything else.** Mortgages, gifts, lease-to-own and developer registrations sit next to
  real sales. One "sale" is a 70.7 sqm flat at AED 920 million.

The first version of this project (v1) was a dashboard built straight on raw rows, and several of its headline
numbers were wrong ([v1 retrospective](docs/V1_RETROSPECTIVE_2023.md)). **This version fixes the process, not just the chart.**

### 2. Data process
```
DLD sales exports  ─┐                     seeds/ (reviewed reference data)
DLD rent exports   ─┤                     ├─ area_name_map.csv         sales communities → DLD land areas
                    ▼                     ├─ transaction_type_rules.csv sale or not, per sub-type, with reason
     pipeline/ingest.py  (load as-is)     └─ unit_type_map.csv         shared unit classes, scope decisions
                    ▼
  models/staging/        typed + renamed, no rows removed
  models/intermediate/   area, unit class and sale rules applied
  models/marts/          fct_sales, fct_rent_contracts, mart_area_unit_kpis, mart_area_segment_kpis, mart_monthly_market
                    ▼
  pipeline/quality_checks.py   23 checks on every refresh → dq_results + reports/data_quality_report.md
                    ▼
  Streamlit app (screening · market · data health · KPI definitions)   |   dbt + Lightdash-ready metrics
```

Design choices that matter for operations:
- **Fix the hierarchy, don't merge names.** "Dubai Marina" and "Marsa Dubai" aren't duplicates: one is a
  community, the other the DLD land area it sits in. `pipeline/propose_area_map.py` links each community to its
  land area **using projects that appear in both files as evidence** (e.g. JVC → Al Barsha South Fourth: 196
  shared projects, 100% agreement). Strong links are applied; 32 weak ones are listed for an owner. Area match rate
  goes from **43% → 90%** of valid sales.
- **One source of truth for rules.** Thresholds are defined once in `dbt_project.yml` and read by dbt, the SQLite
  runner and the quality checks. KPI definitions are written once in `docs/kpi_definitions.yml`, which generates
  the KPI catalogue and the app's definitions tab.
- **Flag, don't delete.** Every excluded record stays in the fact tables with `is_valid = 0` and a reason
  ("out of scope: land or non-residential", "excluded: price per sqm above maximum", …).
- **Real dbt, free hosting.** The SQL in `models/` is a dbt project: `dbt build` passes 27/27 seeds, models and
  tests on DuckDB. Streamlit Cloud runs the same SQL on SQLite through a small runner; both engines produce
  identical marts.

### 3. KPIs
14 KPIs, each with definition, formula, source model, owner and refresh frequency:
**[docs/KPI_CATALOGUE.md](docs/KPI_CATALOGUE.md)**. The screening KPIs:

| KPI | Definition (short) |
|---|---|
| Median ready price / sqm | Median sale price ÷ size, ready units only |
| Gross rental yield | Median rent per sqm ÷ median **ready** sale price per sqm, same area and unit class |
| Yield confidence | Reliable / Indicative / Insufficient data, from the smaller of the two sample sizes |
| Liquidity | Ready (resale) sales per month |
| Area match rate | Share of sales whose area can be compared with rents (pipeline health) |
| Open data incidents | FAIL checks on the latest refresh (target 0 before numbers are shared) |

### 4. Monitoring
`reports/data_quality_report.md` is regenerated on every build: 23 checks across completeness, uniqueness,
validity, scope, the shared area dimension and cross-source coverage. Each comes with rows affected, examples,
next step and owner. The app's **Data health** tab shows the same results. Current run: **0 fail, 13 warn
(all handled by rules, listed for review), 10 pass**.

### 5. Result
- **61,857 residential freehold sales** and **242,427 rent contracts** you can trust, out of 101,884 and 277,351 raw rows.
- **Gross yield for 64 area/unit-class segments covering 81% of valid sales**, 39 of them *Reliable* for
  apartments. Apartment yields range from 4.6% to 9.0% (median 6.3%), in line with published 2026 market ranges.
- Same files, naive method vs governed (generated by the pipeline):

| KPI | Naive (v1 method) | Governed |
|---|---|---|
| Transactions | 100,860 rows | 61,857 sales |
| Total value | AED 277.2B | AED 108.9B |
| Off-plan premium per sqm | 40% | 20% |

Before/after time-to-answer for the same business questions (Excel on raw exports vs this tool):
**[docs/BEFORE_AFTER_TEST.md](docs/BEFORE_AFTER_TEST.md)**. Only measured times are reported there.

### 6. Ask the data (AI assistant)
A LangChain agent in its own tab answers plain-language questions with two tools:

| Tool | What it does | Guardrail |
|---|---|---|
| `run_sql` (text-to-SQL) | Writes and runs SQL for every number | Read-only connection; SQLite authorizer allows `SELECT` on governed tables only, so raw tables and writes are refused by the database, not by the prompt; row and time limits |
| `search_docs` (RAG) | Retrieves KPI definitions, data-quality findings and limitations | Vector search over Gemini embeddings, with a keyword (BM25) fallback |

Every answer shows the SQL it ran and the definitions it used, and the assistant is told to say "the data can't
answer that" instead of guessing. It runs on Gemini's free API tier with per-visit and per-day question limits.
`python -m assistant.evaluate` scores it against answers computed by SQL and writes `docs/ASSISTANT_EVAL.md`.

**Isolation:** the assistant's libraries load only inside its tab. With no API key, a provider outage or a failed
import, that tab shows a notice and the four dashboard tabs keep working. `python scripts/smoke_test.py` checks this
offline before each push.

---

## Refreshing the data
1. On [dubailand.gov.ae → Open Data → Real Estate Data](https://dubailand.gov.ae/en/open-data/real-estate-data):
   **Transactions** (Usage: Residential) and **Rents** (Registration Date, Free Hold: Yes, Usage: Residential).
   The site has a captcha and fails on very large exports, so download rents two months at a time.
2. Save the CSVs (or .csv.gz) into `data/sales/` and `data/rents/`; update `period_*` in `dbt_project.yml`.
3. `python -m pipeline.build`. If check A01 reports new area names, run `python -m pipeline.propose_area_map`
   and review the proposed links before committing.

## Run it
```bash
pip install -r requirements.txt
python -m pipeline.build      # load → models → quality checks → reports (about 10 seconds)
streamlit run app.py          # also rebuilds automatically when any input file changes
python scripts/smoke_test.py  # offline check: build, guardrails, assistant wiring, app loads
```
The assistant tab needs `GEMINI_API_KEY` (free key from Google AI Studio) as an environment variable or in
Streamlit secrets. Never commit it.
With dbt (optional, same models):
```bash
pip install dbt-duckdb
python -m pipeline.load_duckdb
dbt build --profiles-dir .
```

## Project structure
```
app.py                         Streamlit app (5 tabs)
assistant/                     AI assistant: guarded SQL tool, retrieval, agent, evaluation
dbt_project.yml / profiles.yml dbt project + the single place thresholds live
models/  staging/ intermediate/ marts/  schema.yml (tests + Lightdash metric definitions)
seeds/                         reviewed reference data (area crosswalk, sale rules, unit classes)
tests/                         custom dbt tests (yield range, unmapped sub-types, reconciliation)
pipeline/                      ingest, model runner, quality checks, area crosswalk, KPI catalogue, build
docs/                          KPI definitions (YAML), KPI catalogue, before/after test, v1 retrospective
reports/                       data-quality report + run history (generated)
sql/analysis_queries.sql       ad-hoc queries against the governed tables
data/sales/, data/rents/       DLD exports (.csv.gz);  data/archive_2023/ = v1's source file
```

## Known limitations
- Gross yield is before service charges, vacancy, management and DLD fees.
- Yield is per area and unit class, not per bedroom: the Ejari export has no room count for 89% of contracts (flats).
- Rents include renewals, which lag the market; a new-leases-only yield is shown alongside.
- Liquidity is a volume proxy; true time-to-sell needs listing data (days on market) that DLD doesn't publish.
- Rents are freehold only (Stake's scope); sales are filtered to freehold to match.

## Next steps
- Point the dbt project at Lightdash (metrics are already defined in `models/schema.yml`).
- Automate the refresh through the Dubai Pulse API (needs an API key) instead of captcha-protected downloads.
