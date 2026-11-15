-- One row per arm's-length residential SALE (grain: transaction_number).
--   * mortgages, gifts, lease-to-own and developer registrations are excluded by rule
--   * repeated transaction numbers within sales are collapsed to one row
--   * out-of-scope (land, offices, shops, non-freehold) and implausible records are kept
--     but marked is_valid = 0 with the reason, so every exclusion is visible and countable
with market_sales as (
    select *,
        row_number() over (partition by transaction_number order by source_file, source_row) as dup_rank
    from {{ ref('int_transactions_conformed') }}
    where counts_as_market_sale = 1
),

classified as (
    select
        transaction_number,
        source_file,
        source_row,
        transaction_date,
        transaction_month,
        transaction_sub_type,
        registration_type,
        case when registration_type = 'Off-Plan' then 1 else 0 end   as is_off_plan,
        is_free_hold,
        area_name,
        raw_area_name,
        area_mapping_status,
        property_type,
        property_sub_type,
        unit_class,
        rooms,
        bedrooms_band,
        amount_aed,
        transaction_size_sqm,
        price_per_sqm,
        project,
        latitude,
        longitude,
        nearest_metro,
        case
            when property_type = 'Land'
              or unit_class is null or unit_class = 'Out of scope'           then 'out of scope: land or non-residential'
            when is_free_hold <> 'Free Hold'                                  then 'out of scope: non-freehold'
            when transaction_date < '{{ var('period_start') }}'
              or transaction_date > '{{ var('period_end') }} 23:59:59'        then 'out of scope: outside reporting window'
            when transaction_size_sqm is null
              or transaction_size_sqm < {{ var('min_unit_size_sqm') }}       then 'excluded: missing or implausible size'
            when amount_aed < {{ var('min_sale_price_aed') }}                then 'excluded: price below minimum'
            when price_per_sqm < {{ var('min_sale_price_per_sqm') }}         then 'excluded: price per sqm below minimum'
            when price_per_sqm > {{ var('max_sale_price_per_sqm') }}         then 'excluded: price per sqm above maximum'
            when price_per_sqm > {{ var('review_sale_price_per_sqm') }}      then 'kept: very high price per sqm, review'
            else 'ok'
        end as quality_status
    from market_sales
    where dup_rank = 1
)

select
    *,
    case when quality_status like 'excluded%' or quality_status like 'out of scope%' then 0 else 1 end as is_valid
from classified
