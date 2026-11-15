-- New DLD transaction sub-types must get an explicit sale / not-sale decision.
select distinct transaction_type, transaction_sub_type
from {{ ref('int_transactions_conformed') }}
where is_unmapped_type = 1
