-- Monthly market activity. Grain: one row per month.
-- Shows source rows next to real sales so the gap (mortgages, gifts, duplicates,
-- invalid records) is visible every month instead of hidden in a total.
with source_rows as (
    select
        transaction_month,
        count(*)                                                    as source_rows,
        sum(amount_aed)                                             as source_amount_aed
    from {{ ref('int_transactions_conformed') }}
    where transaction_month between substr('{{ var('period_start') }}', 1, 7) and substr('{{ var('period_end') }}', 1, 7)
    group by transaction_month
),

sales as (
    select
        transaction_month,
        count(*)                                                    as sales_count,
        sum(is_off_plan)                                            as off_plan_sales,
        sum(amount_aed)                                             as sales_value_aed,
        median(price_per_sqm)                                       as median_price_per_sqm,
        median(case when is_off_plan = 1 then price_per_sqm end)    as median_off_plan_price_per_sqm,
        median(case when is_off_plan = 0 then price_per_sqm end)    as median_ready_price_per_sqm
    from {{ ref('fct_sales') }}
    where is_valid = 1
    group by transaction_month
)

select
    src.transaction_month,
    src.source_rows,
    src.source_amount_aed,
    coalesce(s.sales_count, 0)                                      as sales_count,
    coalesce(s.off_plan_sales, 0)                                   as off_plan_sales,
    coalesce(s.sales_value_aed, 0)                                  as sales_value_aed,
    s.median_price_per_sqm,
    s.median_off_plan_price_per_sqm,
    s.median_ready_price_per_sqm
from source_rows src
left join sales s
    on src.transaction_month = s.transaction_month
