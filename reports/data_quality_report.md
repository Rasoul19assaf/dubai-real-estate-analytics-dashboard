# Data quality report

_Generated automatically by `python -m pipeline.build` on 2026-11-15 14:30 UTC. Do not edit by hand._

**0 fail · 13 warn · 10 pass**

FAIL = a KPI is wrong or missing until someone acts. WARN = handled by a rule, but someone should know or review. Thresholds live in `dbt_project.yml` → `vars`.

## Open incidents

### 🟡 WARN A03 · Weakly-evidenced area links decided by an owner

- **Dataset:** areas  ·  **Rows affected:** 4,638  ·  **Owner:** Acquisitions (business owner)
- **What we found:** 32 communities share only a few projects with a rent land area, so they are NOT linked automatically (4,638 sales rows). A wrong link silently changes that area's yield.
- **Next step:** Owner confirms or rejects each link in seeds/area_name_map.csv.
- **Examples:**
  - `CITY OF ARABIA (2,558 sales): 2 shared projects, 100% of matched sales -> Wadi Al Safa 4`
  - `DUBAI MARITIME CITY (400 sales): 2 shared projects, 100% of matched sales -> Madinat Dubai Almelaheyah`
  - `WARSAN FIRST (325 sales): 2 shared projects, 100% of matched sales -> Al Warsan First`
  - `DMCC-EZ2 (280 sales): 1 shared projects, 100% of matched sales -> Jabal Ali First`
  - `TECOM SITE A (233 sales): 1 shared projects, 100% of matched sales -> Al Safouh Second`

### 🟡 WARN A04 · Sales areas with no rent evidence at all

- **Dataset:** areas  ·  **Rows affected:** 3,156  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 96 sales area names share no project with any rent contract (often new off-plan communities with nothing rented yet). They get price and liquidity, but no yield.
- **Next step:** Expected for pre-handover areas; recheck after each refresh.
- **Examples:**
  - `HORIZON (622 sales rows)`
  - `BUSINESS PARK (553 sales rows)`
  - `SAMA AL JADAF (485 sales rows)`
  - `DISCOVERY GARDENS (392 sales rows)`
  - `PALM JABAL ALI (302 sales rows)`

### 🟡 WARN R03 · Rent rows are not duplicated

- **Dataset:** rents  ·  **Rows affected:** 25,805  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 25,805 of 277,351 rent rows (9.3%) are exact copies of another row. The DLD rent export has no contract number, so a full-row fingerprint is the only way to catch them. Kept once.
- **Next step:** Report to the data provider; never count raw rows as contracts.

### 🟡 WARN R04 · Rents are single residential units with plausible values

- **Dataset:** rents  ·  **Rows affected:** 9,119  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 4,163 non-standard residential; 4,084 multi-unit contract; 617 rent per sqm below minimum; 220 rent below minimum; 35 missing or implausible size
- **Next step:** Excluded from KPIs automatically (labour camps, whole-building leases, data-entry errors).

### 🟡 WARN R06 · Every rent unit type maps to a unit class

- **Dataset:** rents  ·  **Rows affected:** 41  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 1 rent property sub-types without a unit class (can't join to sales)
- **Next step:** Add to seeds/unit_type_map.csv or confirm they are out of scope.
- **Examples:**
  - `(blank) (41 rows)`

### 🟡 WARN R07 · Bedrooms are known for rent contracts

- **Dataset:** rents  ·  **Rows affected:** 216,384  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 216,384 of 242,427 valid contracts (89%) have no room count: the Ejari export leaves it blank for flats. Handled: yield is computed per area and unit class using rent and price per sqm, not per bedroom.
- **Next step:** Revisit if a richer rent source (e.g. Dubai Pulse API) becomes available.

### 🟡 WARN S03 · Dates fall inside the reporting window

- **Dataset:** sales  ·  **Rows affected:** 206  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 206 rows dated outside 2026-05-01 to 2026-10-31 although the export was requested for exactly that window (the website's date filter and the recorded timestamp disagree). Handled: marked out of scope, so each month's KPIs only contain that month.
- **Next step:** Check how the export filters dates; don't trust the filter for month-end totals.
- **Examples:**
  - `2026-04-30: 206 rows`

### 🟡 WARN S04 · Transaction numbers are unique

- **Dataset:** sales  ·  **Rows affected:** 3,452  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 3,452 rows share 422 transaction numbers. 248 numbers are one deal (mostly lease-to-own) logged twice, once as Sales and once as Mortgage; 13 numbers repeat within Sales (328 rows are exact copies); the rest are portfolio mortgages (see S05). Handled: these sub-types are not market sales, and one row per number reaches the KPIs.
- **Next step:** No action while the rule holds; counting raw rows overstates market activity.

### 🟡 WARN S05 · Portfolio mortgage amounts aren't repeated per unit

- **Dataset:** sales  ·  **Rows affected:** 2,900  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 149 portfolio mortgages repeat the same total amount on every unit (2,900 rows). Summing raw amounts would add AED 8.14B that never changed hands. Handled: mortgages are excluded from sales KPIs by rule.
- **Next step:** Never sum the raw Amount column across transaction types.
- **Examples:**
  - `43-127-2026 (None): 283 rows x AED 1,052,173`
  - `49-41-2026 (AG TOWER): 109 rows x AED 2,416,972`
  - `43-224-2026 (None): 99 rows x AED 252,525`

### 🟡 WARN S07 · Sale prices and sizes are physically possible

- **Dataset:** sales  ·  **Rows affected:** 576  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** 341 price below minimum; 230 missing or implausible size; 4 price per sqm below minimum; 1 price per sqm above maximum. 28 'sales' are under 5 sqm at low prices (e.g. a 2-bed flat at 3 sqm): possibly a share of a unit changing hands rather than a whole unit. Hypothesis, to confirm with DLD.
- **Next step:** Excluded from KPIs automatically; spot-check examples against the DLD site.
- **Examples:**
  - `102-59460-2026 | Al Kifaf | excluded: missing or implausible size | AED 25,438 | 1.05 sqm`
  - `102-41344-2026 | Al Wasl (City Walk) | excluded: missing or implausible size | AED 26,130 | 0.75 sqm`
  - `11-23384-2026 | Marsa Dubai (Dubai Marina, Jumeirah Beach Residence) | excluded: price below minimum | AED 163 | 85.72 sqm`
  - `11-26772-2026 | Al Barsha South Fourth (Jumeirah Village Circle) | excluded: price below minimum | AED 675 | 37.92 sqm`
  - `11-31149-2026 | Marsa Dubai (Dubai Marina, Jumeirah Beach Residence) | excluded: price per sqm above maximum | AED 919,789,428 | 70.74 sqm`
  - `11-23131-2026 | Al Barari | excluded: price per sqm below minimum | AED 104,961 | 149.01 sqm`
  - `11-23438-2026 | Burj Khalifa | excluded: price per sqm below minimum | AED 109,575 | 170.76 sqm`
  - `11-23785-2026 | Hor Al Anz East | out of scope: land or non-residential | AED 53,970 | 21.2 sqm`
  - `11-25599-2026 | Al Barsha South Fourth (Jumeirah Village Circle) | out of scope: land or non-residential | AED 58,771 | 2.73 sqm`
  - `11-26079-2026 | Nadd Hessa (Silicon Oasis) | out of scope: non-freehold | AED 214,678 | 20.94 sqm`
  - `11-16357-2026 | Nadd Hessa (Silicon Oasis) | out of scope: non-freehold | AED 410,000 | 42.83 sqm`
  - `102-41191-2026 | Al Barsha South Fifth (Jumeirah Village Triangle) | out of scope: outside reporting window | AED 489,794 | 29.79 sqm`
  - `11-15043-2026 | Jabal Ali First (Al Furjan) | out of scope: outside reporting window | AED 525,000 | 35.0 sqm`

### 🟡 WARN S08 · Price per sqm above AED 150,000 reviewed

- **Dataset:** sales  ·  **Rows affected:** 3  ·  **Owner:** Acquisitions (business owner)
- **What we found:** 3 sales between AED 150,000 and 500,000 per sqm: kept (real ultra-prime sales exist) but listed for review. Above the maximum they are excluded (S07)
- **Next step:** Confirm or correct; medians keep a few outliers from moving area KPIs.
- **Examples:**
  - `102-64264-2026 | Jumeirah Second | Aman Residences Dubai | AED 166,077,188 (178,384/sqm)`
  - `102-70137-2026 | Jumeirah Second | Aman Residences Dubai | AED 57,555,304 (161,995/sqm)`
  - `102-70153-2026 | Jumeirah Second | Aman Residences Dubai | AED 54,736,514 (153,988/sqm)`

### 🟡 WARN S10 · Export filter 'Usage = Residential' can be trusted

- **Dataset:** sales  ·  **Rows affected:** 8,250  ·  **Owner:** Ops Excellence (data owner)
- **What we found:** The Usage column is blank on 101,884 of 101,884 rows, and sales of land, offices and shops are present although the export was filtered to Residential. 8,018 land or non-residential; 125 outside reporting window; 107 non-freehold. Handled: scope is decided by property type and unit-class rules, not by the export filter.
- **Next step:** Don't rely on the website filter; keep the unit-type rules current.
- **Examples:**
  - `Land / Residential: 2,414 sales`
  - `Unit / Office: 2,102 sales`
  - `Land / Commercial: 1,192 sales`
  - `Land / (blank): 1,000 sales`
  - `Unit / Shop: 702 sales`

### 🟡 WARN X01 · Yield can be computed where buying happens

- **Dataset:** kpis  ·  **Rows affected:** 99  ·  **Owner:** Acquisitions (business owner)
- **What we found:** Yield available for 64 of 163 area/unit-class segments, covering 81% of valid sales (needs at least 10 ready sales and rent contracts per segment)
- **Next step:** Segments without yield show 'Insufficient data' rather than a guess.

## Passing checks

| Check | Dataset | Result |
|---|---|---|
| S01 Every month of the period is present | sales | 101,884 source rows; all 6 months present |
| S02 Required fields (number, date, amount, area) are filled | sales | 0 rows missing a required field |
| S06 Every transaction sub-type has a sale/not-sale rule | sales | 0 rows have a sub-type not in seeds/transaction_type_rules.csv (counted as NOT a sale until reviewed) |
| S09 Studios are recorded as a separate category | sales | 21,905 studio sales out of 70,683 |
| A01 Every area name in sales is in the area map | areas | 0 new area names not in seeds/area_name_map.csv |
| A02 Sales areas line up with rent areas | areas | Sales use community names (e.g. Jumeirah Village Circle); rents use DLD land areas (e.g. Al Barsha South Fourth). On name alone only 43% of valid sales match a rent area. 51 communities are bridged to their land area by shared projects (seeds/area_name_map.csv), bringing coverage to 90%. |
| R01 Rent contracts are loaded | rents | 277,351 rent contract rows loaded from data/rents/ |
| R02 Every month of the period is present (rents) | rents | 277,351 rows covering 6 months; missing: none |
| R08 Registration dates fall inside the reporting window | rents | 0 rent rows dated outside the window |
| R05 Every rent area name is in the area map | rents | 0 rent area names not in the area map |

## Impact of the data rules on headline KPIs

Same source files, computed two ways: the naive v1 method (every row, 0.5/99.5 percentile clip, means) vs governed (residential freehold sales only, de-duplicated, rule-based validity, medians). What v1 actually published on the 2023 file: docs/V1_RETROSPECTIVE_2023.md.

| KPI | Naive (v1 method) | Governed | Why it differs |
|---|---|---|---|
| Transactions | 100,860 rows | 61,857 sales | the naive count includes mortgages, gifts, lease-to-own, developer registrations, land, offices and duplicate rows |
| Total value | AED 277.2B | AED 108.9B | the naive sum adds loan amounts, repeated portfolio-mortgage totals, land and commercial deals |
| Price per sqm (all) | AED 17,513 (mean) | AED 18,248 (median) | residential freehold sales only; median so a few ultra-prime sales don't pull the figure |
| Off-plan premium per sqm | 40% | 20% | the naive ready average mixes in mortgage, gift and land values; on sales alone the same mean-based method gives 21% |
| Records removed | 1,020 (percentile clip) | 576 invalid + 8,250 out of scope (rules) | the clip deletes 16 genuine AED 50M+ sales while keeping 271 records with impossible sizes or prices; rules say why each record is out |
| Distinct area names | 254 | 104 | sales communities linked to their DLD land area, so they join to rents |
