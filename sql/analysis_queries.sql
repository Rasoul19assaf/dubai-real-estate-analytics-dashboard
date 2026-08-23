-- Dubai Residential Real Estate — Analysis Queries
-- Database: data/dubai_real_estate.db (table: transactions)
-- Source data: Dubai Land Department open transaction records, Jan-Jun 2023
--
-- These queries back the KPI tiles and charts in the Streamlit dashboard
-- (app.py) and can also be run standalone with `sqlite3 data/dubai_real_estate.db`.

-- 1. Headline KPIs: total transactions, total value, average price per sqm
SELECT
    COUNT(*)                              AS total_transactions,
    ROUND(SUM(amount_aed) / 1e9, 2)       AS total_value_aed_bn,
    ROUND(AVG(price_per_sqm), 0)          AS avg_price_per_sqm_aed,
    ROUND(AVG(amount_aed), 0)             AS avg_transaction_value_aed
FROM transactions;

-- 2. Monthly transaction volume and value trend
SELECT
    transaction_month,
    COUNT(*)                        AS transactions,
    ROUND(SUM(amount_aed) / 1e6, 1) AS total_value_aed_mn,
    ROUND(AVG(price_per_sqm), 0)    AS avg_price_per_sqm_aed
FROM transactions
GROUP BY transaction_month
ORDER BY transaction_month;

-- 3. Top 10 areas by transaction volume, with average price per sqm
SELECT
    area,
    COUNT(*)                     AS transactions,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm_aed,
    ROUND(AVG(amount_aed), 0)    AS avg_transaction_value_aed
FROM transactions
GROUP BY area
HAVING transactions >= 50
ORDER BY transactions DESC
LIMIT 10;

-- 4. Top 10 areas by average price per sqm (min 50 transactions, to avoid noise
--    from areas with only a handful of sales)
SELECT
    area,
    COUNT(*)                     AS transactions,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm_aed
FROM transactions
GROUP BY area
HAVING transactions >= 50
ORDER BY avg_price_per_sqm_aed DESC
LIMIT 10;

-- 5. Off-plan vs. ready split, by transaction count and average price per sqm
SELECT
    registration_type,
    COUNT(*)                        AS transactions,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM transactions), 1) AS pct_of_total,
    ROUND(AVG(price_per_sqm), 0)    AS avg_price_per_sqm_aed
FROM transactions
GROUP BY registration_type
ORDER BY transactions DESC;

-- 6. Property sub-type mix (Flat, Villa, Hotel Apartment, ...)
SELECT
    property_sub_type,
    COUNT(*)                     AS transactions,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm_aed,
    ROUND(AVG(amount_aed), 0)    AS avg_transaction_value_aed
FROM transactions
GROUP BY property_sub_type
ORDER BY transactions DESC;

-- 7. Bedroom-count distribution and its relationship to average transaction value
SELECT
    rooms,
    COUNT(*)                     AS transactions,
    ROUND(AVG(amount_aed), 0)    AS avg_transaction_value_aed,
    ROUND(AVG(transaction_size_sqm), 0) AS avg_size_sqm
FROM transactions
GROUP BY rooms
ORDER BY transactions DESC;

-- 8. Areas with the sharpest month-on-month price/sqm movement (window function),
--    restricted to areas with meaningful monthly volume
WITH monthly_area AS (
    SELECT
        area,
        transaction_month,
        AVG(price_per_sqm) AS avg_price_per_sqm,
        COUNT(*)           AS transactions
    FROM transactions
    GROUP BY area, transaction_month
    HAVING transactions >= 15
),
with_change AS (
    SELECT
        area,
        transaction_month,
        avg_price_per_sqm,
        LAG(avg_price_per_sqm) OVER (PARTITION BY area ORDER BY transaction_month) AS prev_price_per_sqm
    FROM monthly_area
)
SELECT
    area,
    transaction_month,
    ROUND(avg_price_per_sqm, 0) AS avg_price_per_sqm_aed,
    ROUND(100.0 * (avg_price_per_sqm - prev_price_per_sqm) / prev_price_per_sqm, 1) AS pct_change_mom
FROM with_change
WHERE prev_price_per_sqm IS NOT NULL
ORDER BY ABS(pct_change_mom) DESC
LIMIT 15;

-- 9. Proximity effect: does being near a metro station correlate with price/sqm?
SELECT
    CASE WHEN nearest_metro IS NOT NULL THEN 'Near metro (listed)' ELSE 'No metro listed' END AS metro_proximity,
    COUNT(*)                     AS transactions,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm_aed
FROM transactions
GROUP BY metro_proximity;
