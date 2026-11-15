# KPI catalogue

_Generated from `docs/kpi_definitions.yml` by `python -m pipeline.build`. Edit the YAML, not this file._

- **Refresh:** Weekly (DLD publishes daily; weekly is enough for acquisition decisions)
- **Data owner (all KPIs):** Ops Excellence (pipeline, definitions, data quality)
- **Business owners** are proposed roles, to be confirmed with the team.
- **Thresholds** (`dbt_project.yml` → `vars`): min sale price AED 100,000; price/sqm floor AED 1,000; review above AED 150,000/sqm; KPI shown as *Reliable* from n = 30, *Indicative* from n = 10.

| ID | KPI | Question it answers | Unit | Business owner |
|---|---|---|---|---|
| K01 | Valid sales | How much buying activity is there? | count | Acquisitions |
| K02 | Sales value | How much money changed hands? | AED | Acquisitions |
| K03 | Median sale price | What does a typical unit cost? | AED | Acquisitions |
| K04 | Median price per sqm | Is this area expensive for what you get? | AED per sqm | Acquisitions |
| K05 | Off-plan premium | How much more does off-plan cost than ready? | percent | Acquisitions |
| K06 | Off-plan share | How much of the activity is off-plan? | percent | Acquisitions |
| K07 | Liquidity (sales per month) | If we buy here, how easily could a unit be sold again? | sales per month | Acquisitions |
| K08 | Median annual rent | What rent does a typical unit earn? | AED per year | Property / Asset management |
| K09 | Median rent per sqm | Rent normalised for unit size. | AED per sqm per year | Property / Asset management |
| K10 | Gross rental yield | What return before costs should we expect if we buy here? | percent per year | Acquisitions |
| K11 | Yield confidence | Can we trust this yield figure? | label | Ops Excellence |
| K12 | Valid-sale rate | How much of the source data can we use? | percent | Ops Excellence |
| K14 | Area match rate | How much of the sales market can be compared with rents? | percent | Ops Excellence |
| K13 | Open data incidents | Is anything blocking correct numbers right now? | count | Ops Excellence |

## K01 · Valid sales

**Definition.** Number of distinct arm's-length residential sales that pass the validity rules.

**Formula.** `COUNT(DISTINCT transaction_number) WHERE is_valid = 1`

**Source model.** `fct_sales` · **Unit.** count · **Business owner.** Acquisitions · **Refresh.** Weekly · **Lightdash metric:** yes

**Watch out.** Residential freehold units only. Excludes mortgages, gifts, lease-to-own, developer registrations, land and commercial units. Raw DLD row counts are far higher (see the data-quality report).

## K02 · Sales value

**Definition.** Sum of sale prices of valid sales.

**Formula.** `SUM(amount_aed) WHERE is_valid = 1`

**Source model.** `fct_sales` · **Unit.** AED · **Business owner.** Acquisitions · **Refresh.** Weekly · **Lightdash metric:** yes

**Watch out.** Never sum the raw Amount column; it mixes loan amounts and repeats portfolio-mortgage totals per unit.

## K03 · Median sale price

**Definition.** Median sale price of valid sales in the segment.

**Formula.** `MEDIAN(amount_aed) WHERE is_valid = 1`

**Source model.** `fct_sales / mart_area_segment_kpis` · **Unit.** AED · **Business owner.** Acquisitions · **Refresh.** Weekly · **Lightdash metric:** yes

**Watch out.** Depends on unit-size mix; compare within the same unit class and bedroom count.

## K04 · Median price per sqm

**Definition.** Median of sale price divided by transaction size (sqm).

**Formula.** `MEDIAN(amount_aed / transaction_size_sqm) WHERE is_valid = 1`

**Source model.** `fct_sales / mart_area_segment_kpis` · **Unit.** AED per sqm · **Business owner.** Acquisitions · **Refresh.** Weekly · **Lightdash metric:** yes

**Watch out.** Median, not mean, so a handful of ultra-prime sales can't move an area figure.

## K05 · Off-plan premium

**Definition.** Median off-plan price per sqm divided by median ready price per sqm, minus 1.

**Formula.** `MEDIAN(psm | off-plan) / MEDIAN(psm | ready) - 1`

**Source model.** `mart_monthly_market` · **Unit.** percent · **Business owner.** Acquisitions · **Refresh.** Weekly

**Watch out.** Market-wide figure mixes different areas and projects; not a like-for-like premium.

## K06 · Off-plan share

**Definition.** Share of valid sales registered as off-plan.

**Formula.** `AVG(is_off_plan) WHERE is_valid = 1`

**Source model.** `fct_sales / mart_area_segment_kpis` · **Unit.** percent · **Business owner.** Acquisitions · **Refresh.** Weekly · **Lightdash metric:** yes

## K07 · Liquidity (sales per month)

**Definition.** Valid sales per month in the segment; the ready-only version measures the resale market.

**Formula.** `COUNT(valid sales) / months_in_period   (ready_sales_per_month uses is_off_plan = 0)`

**Source model.** `mart_area_unit_kpis / mart_area_segment_kpis` · **Unit.** sales per month · **Business owner.** Acquisitions · **Refresh.** Weekly

**Watch out.** A volume proxy. True time-to-sell needs listing data (days on market), which DLD does not publish.

## K08 · Median annual rent

**Definition.** Median DLD-annualised rent of valid single-unit residential Ejari contracts.

**Formula.** `MEDIAN(annual_rent_aed) WHERE is_valid = 1`

**Source model.** `fct_rent_contracts / mart_area_unit_kpis` · **Unit.** AED per year · **Business owner.** Property / Asset management · **Refresh.** Weekly · **Lightdash metric:** yes

**Watch out.** Includes new and renewed contracts; renewals lag the market when rents are rising.

## K09 · Median rent per sqm

**Definition.** Median of annual rent divided by property size (sqm).

**Formula.** `MEDIAN(annual_rent_aed / property_size_sqm) WHERE is_valid = 1`

**Source model.** `fct_rent_contracts / mart_area_unit_kpis` · **Unit.** AED per sqm per year · **Business owner.** Property / Asset management · **Refresh.** Weekly · **Lightdash metric:** yes

## K10 · Gross rental yield

**Definition.** Median rent per sqm divided by median READY sale price per sqm, for the same area and unit class.

**Formula.** `median_rent_per_sqm / median_ready_price_per_sqm   (gross_yield_new_leases uses new contracts only)`

**Source model.** `mart_area_unit_kpis` · **Unit.** percent per year · **Business owner.** Acquisitions · **Refresh.** Weekly

**Watch out.** Gross; before service charges, vacancy, management fees and DLD fees. Not by bedroom, because the Ejari export has no room count for most flats; per-sqm values keep unit size from biasing it. Includes renewals, which lag market rents; compare with the new-leases version. Shown only when both samples reach min_sample_indicative.

## K11 · Yield confidence

**Definition.** Reliable if the smaller of (ready sales, rent contracts) >= min_sample_reliable; Indicative if >= min_sample_indicative; otherwise Insufficient data.

**Formula.** `CASE on LEAST(ready_sales_count, rent_contracts)`

**Source model.** `mart_area_unit_kpis` · **Unit.** label · **Business owner.** Ops Excellence · **Refresh.** Weekly

**Watch out.** Thresholds in dbt_project.yml vars.

## K12 · Valid-sale rate

**Definition.** Valid sales as a share of all rows in the DLD extract.

**Formula.** `COUNT(fct_sales WHERE is_valid = 1) / COUNT(stg_dld_transactions)`

**Source model.** `mart_monthly_market` · **Unit.** percent · **Business owner.** Ops Excellence · **Refresh.** Weekly

**Watch out.** A pipeline-health KPI. A sudden drop usually means the export settings or source format changed.

## K14 · Area match rate

**Definition.** Share of valid sales whose area is a DLD land area or is linked to one by the area crosswalk.

**Formula.** `COUNT(valid sales WHERE area_mapping_status IN (land_area, project_crosswalk)) / COUNT(valid sales)`

**Source model.** `fct_sales + seeds/area_name_map.csv` · **Unit.** percent · **Business owner.** Ops Excellence · **Refresh.** Weekly

**Watch out.** Sales and rents name areas at different levels (community vs DLD land area). On name alone the match rate is under half.

## K13 · Open data incidents

**Definition.** Number of data-quality checks with status FAIL on the latest refresh.

**Formula.** `COUNT(dq_results WHERE status = 'FAIL')`

**Source model.** `dq_results` · **Unit.** count · **Business owner.** Ops Excellence · **Refresh.** Weekly

**Watch out.** Target is 0 before any KPI is shared outside the team.
