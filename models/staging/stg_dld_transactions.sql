-- Staging: one row per row of the DLD transactions export(s), typed and renamed.
-- No rows are removed here; every decision about what to keep happens downstream
-- and is reported by the data-quality checks.
select
    transaction_number,
    row_hash,
    source_file,
    cast(source_row as integer)                          as source_row,
    transaction_date,
    substr(transaction_date, 1, 7)                       as transaction_month,
    trim(transaction_type)                               as transaction_type,
    trim(transaction_sub_type)                           as transaction_sub_type,
    trim(registration_type)                              as registration_type,
    trim(is_free_hold)                                   as is_free_hold,
    trim(usage)                                          as usage,
    trim(area)                                           as raw_area_name,
    upper(trim(area))                                    as raw_area_key,
    trim(property_type)                                  as property_type,
    trim(property_sub_type)                              as property_sub_type,
    cast(replace(trim(amount), ',', '') as double)       as amount_aed,
    cast(transaction_size_sqm as double)                 as transaction_size_sqm,
    cast(property_size_sqm as double)                    as property_size_sqm,
    trim(rooms)                                          as rooms,
    trim(nearest_metro)                                  as nearest_metro,
    trim(project)                                        as project,
    trim(master_project)                                 as master_project,
    cast(latitude_project as double)                     as latitude,
    cast(longitude_project as double)                    as longitude
from {{ source('dld', 'raw_dld_transactions') }}
