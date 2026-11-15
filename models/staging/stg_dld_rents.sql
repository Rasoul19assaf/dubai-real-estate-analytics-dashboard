-- Staging: one row per Ejari rent contract row in the DLD export(s), typed and renamed.
-- annual_amount is DLD's own annualised value (it rescales contracts that are not 12 months).
-- The dubailand.gov.ae export has no contract number, so row_hash identifies exact duplicates.
select
    ejari_contract_number                                as contract_number,
    row_hash,
    source_file,
    cast(source_row as integer)                          as source_row,
    registration_date,
    substr(registration_date, 1, 7)                      as registration_month,
    start_date,
    end_date,
    trim(version)                                        as version,
    trim(area)                                           as raw_area_name,
    upper(trim(area))                                    as raw_area_key,
    cast(replace(trim(contract_amount), ',', '') as double)   as contract_amount_aed,
    cast(replace(trim(annual_amount), ',', '') as double)     as annual_rent_aed,
    trim(is_free_hold)                                   as is_free_hold,
    cast(replace(trim(property_size_sqm), ',', '') as double) as property_size_sqm,
    trim(property_type)                                  as property_type,
    trim(property_sub_type)                              as property_sub_type,
    trim(number_of_rooms)                                as number_of_rooms,
    trim(usage)                                          as usage,
    cast(no_of_units as integer)                         as no_of_units,
    trim(project)                                        as project,
    trim(master_project)                                 as master_project
from {{ source('dld', 'raw_dld_rents') }}
