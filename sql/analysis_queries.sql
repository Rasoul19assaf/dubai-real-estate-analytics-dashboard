-- Dubai property data: ad-hoc analysis queries against the governed layer
-- Database: data/dubai_real_estate.db (build with `python -m pipeline.build`)
-- Queries 2, 3, 4, 6, 7 run in any SQL client against the SQLite file. Queries 1 and 5
-- use MEDIAN(), which DuckDB (data/dbt.duckdb) and most warehouses have and plain SQLite lacks.
--
-- Rule of thumb: query fct_* and mart_* tables, never the raw_* tables. The raw
-- tables contain mortgages, gifts, duplicates and implausible records that the
-- models already handle (see reports/data_quality_report.md).

-- 1. Headline KPIs (K01, K02, K04)
SELECT
    COUNT(*)                                  AS valid_sales,
    ROUND(SUM(amount_aed) / 1e9, 2)           AS sales_value_aed_bn,
    ROUND(MEDIAN(price_per_sqm), 0)           AS median_price_per_sqm
FROM fct_sales
WHERE is_valid = 1;

-- 2. Monthly activity: source rows vs real sales (K12 valid-sale rate)
SELECT
    transaction_month,
    source_rows,
    sales_count,
    ROUND(100.0 * sales_count / source_rows, 1) AS valid_sale_rate_pct,
    ROUND(median_off_plan_price_per_sqm / median_ready_price_per_sqm - 1, 3) AS off_plan_premium
FROM mart_monthly_market
ORDER BY transaction_month;

-- 3. Screening shortlist: apartments with a median ready price under AED 1.5M, a liquid resale
--    market, and a yield we can trust, ranked by gross yield
SELECT
    area_name,
    ROUND(median_ready_price_aed)            AS median_ready_price_aed,
    ROUND(ready_sales_per_month, 1)          AS ready_sales_per_month,
    ROUND(median_annual_rent_aed)            AS median_annual_rent_aed,
    ROUND(100 * gross_yield, 1)              AS gross_yield_pct,
    ROUND(100 * gross_yield_new_leases, 1)   AS gross_yield_new_leases_pct,
    yield_confidence
FROM mart_area_unit_kpis
WHERE unit_class = 'Apartment'
  AND median_ready_price_aed <= 1500000
  AND ready_sales_per_month >= 5
  AND yield_confidence = 'Reliable'
ORDER BY gross_yield DESC
LIMIT 20;

-- 4. Liquidity ranking: where could an apartment be resold most easily?
SELECT area_name, ROUND(ready_sales_per_month, 1) AS ready_sales_per_month,
       ROUND(median_ready_price_per_sqm) AS ready_price_per_sqm
FROM mart_area_unit_kpis
WHERE unit_class = 'Apartment'
ORDER BY ready_sales_per_month DESC
LIMIT 10;

-- 5. Month-on-month change in median price/sqm by area (window function)
WITH monthly AS (
    SELECT area_name, transaction_month, COUNT(*) AS sales, MEDIAN(price_per_sqm) AS median_psqm
    FROM fct_sales WHERE is_valid = 1
    GROUP BY area_name, transaction_month
)
SELECT area_name, transaction_month, sales, ROUND(median_psqm) AS median_psqm,
       ROUND(100.0 * (median_psqm / LAG(median_psqm) OVER (PARTITION BY area_name ORDER BY transaction_month) - 1), 1)
           AS mom_change_pct
FROM monthly
WHERE area_name IN ('Al Barsha South Fourth (Jumeirah Village Circle)', 'Business Bay', 'Burj Khalifa')
ORDER BY area_name, transaction_month;

-- 6. Open data incidents (K13): what needs a decision before numbers go out?
SELECT check_id, check_name, status, failing_rows, owner, action
FROM dq_results
WHERE status <> 'PASS'
ORDER BY CASE status WHEN 'FAIL' THEN 0 ELSE 1 END, check_id;

-- 7. The area hierarchy: which sales communities were linked to which DLD land area, and on what evidence
SELECT raw_area_key AS sales_area_name, area_name AS reporting_area, mapping_status, evidence
FROM area_name_map
WHERE mapping_status IN ('project_crosswalk', 'alias_pending_review')
ORDER BY CAST(sales_rows_at_review AS INTEGER) DESC
LIMIT 15;

-- 8. Why "count the rows" is wrong: transaction numbers that appear more than once
SELECT transaction_number, COUNT(*) AS rows_,
       MIN(transaction_type || ': ' || transaction_sub_type)
         || CASE WHEN COUNT(DISTINCT transaction_type) > 1
                 THEN ' + ' || MAX(transaction_type || ': ' || transaction_sub_type) ELSE '' END AS logged_as,
       COUNT(DISTINCT amount_aed) AS distinct_amounts
FROM stg_dld_transactions
GROUP BY transaction_number
HAVING COUNT(*) > 1
ORDER BY rows_ DESC
LIMIT 10;
