-- Price and liquidity by bedrooms. Grain: area_name x unit_class x bedrooms_band.
-- (Rental yield lives in mart_area_unit_kpis: the rent export has no bedroom count for most flats.)
select
    area_name,
    unit_class,
    bedrooms_band,
    count(*)                                                         as sales_count,
    sum(case when is_off_plan = 0 then 1 else 0 end)                 as ready_sales_count,
    count(*) * 1.0 / {{ var('months_in_period') }}                  as sales_per_month,
    sum(case when is_off_plan = 0 then 1 else 0 end) * 1.0 / {{ var('months_in_period') }} as ready_sales_per_month,
    avg(is_off_plan * 1.0)                                           as off_plan_share,
    median(amount_aed)                                               as median_price_aed,
    median(price_per_sqm)                                            as median_price_per_sqm,
    median(case when is_off_plan = 0 then amount_aed end)            as median_ready_price_aed,
    median(case when is_off_plan = 0 then price_per_sqm end)         as median_ready_price_per_sqm
from {{ ref('fct_sales') }}
where is_valid = 1
  and bedrooms_band is not null
group by area_name, unit_class, bedrooms_band
