-- A gross yield below 1% or above 20% for a whole segment means a join or unit
-- problem (e.g. rents matched to the wrong area), not a real market signal.
select area_name, unit_class, gross_yield
from {{ ref('mart_area_unit_kpis') }}
where gross_yield is not null
  and (gross_yield < 0.01 or gross_yield > 0.20)
