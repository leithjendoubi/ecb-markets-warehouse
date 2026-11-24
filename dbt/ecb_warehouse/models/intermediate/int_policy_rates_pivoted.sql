-- ECB key rates pivoted to one row per observed date (DFR, MRO fixed rate, MLF); NULL where the source has
-- no observation for that rate on that date (e.g. MRR_FR 2000-06-28..2008-10-14, variable-rate tenders).
select
    rate_date,
    max(rate_pct) filter (where rate_code = 'DFR') as dfr_pct,
    max(rate_pct) filter (where rate_code = 'MRR_FR') as mro_pct,
    max(rate_pct) filter (where rate_code = 'MLFR') as mlf_pct
from {{ ref('stg_ecb__fm') }}
group by rate_date
