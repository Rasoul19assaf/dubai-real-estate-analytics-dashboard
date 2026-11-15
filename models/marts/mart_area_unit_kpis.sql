-- Acquisition screening mart.
-- Grain: one row per area_name x unit_class (Apartment, Villa/Townhouse, ...).
-- Answers: what does it cost, what rent does it earn, how easy is it to buy/sell there.
-- Yield is at this grain (not by bedrooms) because the Ejari export gives no room count for
-- most flats; using price and rent PER SQM keeps unit-size differences from biasing the ratio.
with sales as (
    select
        area_name,
        unit_class,
        count(*)                                                         as sales_count,
        sum(case when is_off_plan = 0 then 1 else 0 end)                 as ready_sales_count,
        avg(is_off_plan * 1.0)                                           as off_plan_share,
        median(amount_aed)                                               as median_price_aed,
        median(price_per_sqm)                                            as median_price_per_sqm,
        median(case when is_off_plan = 0 then amount_aed end)            as median_ready_price_aed,
        median(case when is_off_plan = 0 then price_per_sqm end)         as median_ready_price_per_sqm
    from {{ ref('fct_sales') }}
    where is_valid = 1
    group by area_name, unit_class
),

rents as (
    select
        area_name,
        unit_class,
        count(*)                                                         as rent_contracts,
        sum(case when version = 'New' then 1 else 0 end)                 as new_rent_contracts,
        median(annual_rent_aed)                                          as median_annual_rent_aed,
        median(rent_per_sqm)                                             as median_rent_per_sqm,
        median(case when version = 'New' then rent_per_sqm end)          as median_new_rent_per_sqm
    from {{ ref('fct_rent_contracts') }}
    where is_valid = 1
    group by area_name, unit_class
),

joined as (
    select
        s.*,
        s.sales_count * 1.0 / {{ var('months_in_period') }}             as sales_per_month,
        s.ready_sales_count * 1.0 / {{ var('months_in_period') }}       as ready_sales_per_month,
        coalesce(r.rent_contracts, 0)                                    as rent_contracts,
        coalesce(r.new_rent_contracts, 0)                                as new_rent_contracts,
        r.median_annual_rent_aed,
        r.median_rent_per_sqm,
        r.median_new_rent_per_sqm,
        -- the smaller of the two samples decides how far the yield can be trusted
        case when coalesce(r.rent_contracts, 0) < s.ready_sales_count
             then coalesce(r.rent_contracts, 0) else s.ready_sales_count end as yield_sample
    from sales s
    left join rents r
        on  s.area_name = r.area_name
        and s.unit_class = r.unit_class
)

select
    *,
    -- Gross yield = annual rent / purchase price, both per sqm so unit-size mix cancels out.
    -- READY sale prices only: off-plan units cannot be rented yet and price in a premium.
    case when yield_sample >= {{ var('min_sample_indicative') }}
         then median_rent_per_sqm / median_ready_price_per_sqm end       as gross_yield,
    -- Same, using only NEW leases (renewals lag the market when rents are rising)
    case when yield_sample >= {{ var('min_sample_indicative') }} and new_rent_contracts >= {{ var('min_sample_indicative') }}
         then median_new_rent_per_sqm / median_ready_price_per_sqm end   as gross_yield_new_leases,
    case
        when yield_sample >= {{ var('min_sample_reliable') }}   then 'Reliable'
        when yield_sample >= {{ var('min_sample_indicative') }} then 'Indicative'
        else 'Insufficient data'
    end                                                                  as yield_confidence
from joined
