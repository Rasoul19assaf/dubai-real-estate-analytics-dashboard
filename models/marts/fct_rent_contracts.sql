-- One row per single-unit residential Ejari rent contract.
-- Exact duplicate rows in the export are kept once (row_hash). Multi-unit contracts,
-- labour camps / staff accommodation and implausible records stay with is_valid = 0.
with rents as (
    select
        r.*,
        coalesce(a.area_name, r.raw_area_name)                      as area_name,
        coalesce(a.mapping_status, 'unmapped')                      as area_mapping_status,
        u.unit_class,
        r.annual_rent_aed / nullif(r.property_size_sqm, 0)          as rent_per_sqm,
        row_number() over (partition by r.row_hash order by r.source_file, r.source_row) as dup_rank
    from {{ ref('stg_dld_rents') }} r
    left join {{ ref('area_name_map') }} a
        on r.raw_area_key = a.raw_area_key
    left join {{ ref('unit_type_map') }} u
        on u.source = 'rents' and r.property_sub_type = u.raw_property_sub_type
),

classified as (
    select
        row_hash,
        contract_number,
        source_file,
        source_row,
        registration_date,
        registration_month,
        start_date,
        end_date,
        version,
        area_name,
        raw_area_name,
        area_mapping_status,
        property_type,
        property_sub_type,
        unit_class,
        number_of_rooms,
        case
            when property_sub_type = 'Studio' then 'Studio'
            when cast(number_of_rooms as integer) >= 5 then '5+'
            when cast(number_of_rooms as integer) between 1 and 4 then number_of_rooms
            else null   -- the Ejari export gives no room count for most flats
        end                                                         as bedrooms_band,
        no_of_units,
        property_size_sqm,
        annual_rent_aed,
        rent_per_sqm,
        case
            when unit_class is null or unit_class = 'Out of scope'         then 'out of scope: non-standard residential'
            when coalesce(no_of_units, 1) > 1                              then 'out of scope: multi-unit contract'
            when property_size_sqm is null
              or property_size_sqm < {{ var('min_unit_size_sqm') }}        then 'excluded: missing or implausible size'
            when annual_rent_aed is null
              or annual_rent_aed < {{ var('min_annual_rent_aed') }}        then 'excluded: rent below minimum'
            when rent_per_sqm < {{ var('min_rent_per_sqm') }}              then 'excluded: rent per sqm below minimum'
            when rent_per_sqm > {{ var('review_rent_per_sqm') }}           then 'kept: very high rent per sqm, review'
            else 'ok'
        end as quality_status
    from rents
    where dup_rank = 1
)

select
    *,
    case when quality_status like 'excluded%' or quality_status like 'out of scope%' then 0 else 1 end as is_valid
from classified
