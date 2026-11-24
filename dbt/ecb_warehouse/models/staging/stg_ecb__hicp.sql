-- Euro-area HICP, all items, annual rate of change (percent), one row per month.
with latest as (
    {{ latest_observation(source('raw', 'hicp')) }}
)

select
    series_key,
    time_period,
    cast(time_period || '-01' as date) as month_start,
    cast(obs_value as numeric(9, 4)) as hicp_yoy_pct,
    obs_status,
    load_id,
    extracted_at
from latest
