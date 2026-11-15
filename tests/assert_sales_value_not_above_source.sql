-- Reconciliation: governed sales value can never exceed the raw amount it came from.
select 1
from (select sum(amount_aed) v from {{ ref('fct_sales') }} where is_valid = 1) s,
     (select sum(amount_aed) v from {{ ref('stg_dld_transactions') }}) r
where s.v > r.v
