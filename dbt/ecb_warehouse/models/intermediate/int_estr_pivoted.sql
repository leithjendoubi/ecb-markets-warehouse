-- EUR STR rate and volume side by side, one row per TARGET business day.
select
    obs_date,
    max(obs_value) filter (where measure_code = 'WT') as estr_pct,
    max(obs_value) filter (where measure_code = 'TT') as total_volume_eur_mn
from {{ ref('stg_ecb__est') }}
group by obs_date
