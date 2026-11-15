# v1 retrospective: what the first dashboard got wrong (2023 data)

The first version of this project (v1) was a Streamlit dashboard built directly on 44,745 raw DLD rows for Jan–Jun 2023 (public mirror of the DLD export, kept in `data/archive_2023/`). Rebuilding it with governed rules on the **same file** changed these headline numbers:

| KPI | v1 dashboard | Governed (v2 rules) | Why it moved |
|---|---|---|---|
| Transactions | 44,285 rows | 37,080 sales | v1 counted mortgages, gifts, lease-to-own and developer registrations as transactions, and counted lease-to-own deals twice (once as Sales, once as Mortgage) |
| Total value | AED 97.2B | AED 93.3B | v1 summed loan amounts and repeated portfolio-mortgage totals on top of sale prices |
| Price per sqm (all) | AED 17,454 (mean) | AED 17,044 (median) | sales only; median so a few ultra-prime sales don't pull the figure |
| Off-plan premium per sqm | 39% | 28% | v1's ready average mixed in mortgage and gift values, which sit well below sale prices; on sales alone the same mean-based method gives 25% |
| Records removed as outliers | 448 (percentile clip) | 41 (rule-based) | v1's clip deleted 49 genuine AED 50M+ sales (e.g. Bulgari Lighthouse Dubai) while keeping 21 records with impossible sizes (under 15 sqm) |
| Distinct area names | 107 | 105 | case variants merged; possible aliases listed for an owner instead of guessed |

## Issues found in the 2023 file

| Check | Status | Rows | Finding |
|---|---|---|---|
| S04 Transaction numbers are unique | WARN | 1,439 | 1,439 rows share 134 transaction numbers. 90 numbers are one deal (mostly lease-to-own) logged twice, once as Sales and once as Mortgage; 3 numbers repeat within Sales (2 rows are exact copies); the rest are portfolio mortgages (see S05). Handled: these sub-types are not market sales, and one row per number reaches the KPIs. |
| S05 Portfolio mortgage amounts aren't repeated per unit | WARN | 1,253 | 41 portfolio mortgages repeat the same total amount on every unit (1,253 rows). Summing raw amounts would add AED 2.20B that never changed hands. Handled: mortgages are excluded from sales KPIs by rule. |
| S07 Sale prices and sizes are physically possible | WARN | 41 | 25 missing or implausible size; 15 price below minimum; 1 price per sqm below minimum. 16 'sales' are under 5 sqm at low prices (e.g. a 2-bed flat at 3 sqm): possibly a share of a unit changing hands rather than a whole unit. Hypothesis, to confirm with DLD. |
| S08 Price per sqm above AED 150,000 reviewed | WARN | 1 | 1 sales above the review threshold: kept (real ultra-prime sales exist) but listed for review |
| S09 Studios are recorded as a separate category | WARN | 37,121 | 0 studio sales out of 37,121. Zero studios is unlikely for Dubai; the extract may code studios as 1-bedroom. |
| A02 Same area spelled two ways (case only) is merged | WARN | 2 | 2 areas arrive under two spellings; merged via the area map |
| A03 Possible area aliases decided by an owner | WARN | 5 | 5 area names may be another name for an existing area. NOT merged automatically: a wrong merge silently changes area KPIs. |
| A04 Each project sits in one area | WARN | 5 | 5 projects appear under more than one area name (evidence for A03, or two buildings sharing a name) |

Note: "DUBAI MARINA" vs "Marsa Dubai" was flagged here as a possible alias. The 2026 data resolved it: they are two levels of DLD's area hierarchy (community vs official land area), linked by 47 shared projects. See the area crosswalk in the current pipeline.

_Generated from the pipeline on the 2023 file, before the switch to 2026 DLD exports._
