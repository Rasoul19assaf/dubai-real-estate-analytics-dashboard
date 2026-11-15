-- Conform transactions to shared definitions:
--   * area names  -> seeds/area_name_map.csv         (sales communities bridged to DLD land areas)
--   * unit class  -> seeds/unit_type_map.csv         (same unit classes for sales and rents)
--   * sale or not -> seeds/transaction_type_rules.csv (one reviewed rule per sub-type)
-- Unmapped values are not dropped; they are flagged so the quality checks raise them.
select
    t.*,
    coalesce(a.area_name, t.raw_area_name)                         as area_name,
    coalesce(a.mapping_status, 'unmapped')                         as area_mapping_status,
    u.unit_class,
    coalesce(cast(r.counts_as_market_sale as integer), 0)          as counts_as_market_sale,
    case when r.transaction_sub_type is null then 1 else 0 end     as is_unmapped_type,
    t.amount_aed / nullif(t.transaction_size_sqm, 0)               as price_per_sqm,
    case
        when upper(t.rooms) = 'STUDIO' then 'Studio'
        when t.rooms like '% B/R' then
            case when cast(substr(t.rooms, 1, instr(t.rooms, ' ') - 1) as integer) >= 5 then '5+'
                 else substr(t.rooms, 1, instr(t.rooms, ' ') - 1) end
        else null
    end                                                            as bedrooms_band
from {{ ref('stg_dld_transactions') }} t
left join {{ ref('area_name_map') }} a
    on t.raw_area_key = a.raw_area_key
left join {{ ref('unit_type_map') }} u
    on u.source = 'sales' and t.property_sub_type = u.raw_property_sub_type
left join {{ ref('transaction_type_rules') }} r
    on t.transaction_type = r.transaction_type
   and t.transaction_sub_type = r.transaction_sub_type
