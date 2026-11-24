-- ECB key interest rates, percent. The API returns one row per calendar day (not only change dates).
with latest as (
    {{ latest_observation(source('raw', 'fm')) }}
)

select
    series_key,
    time_period,
    provider_fm_id as rate_code,
    cast(time_period as date) as rate_date,
    cast(obs_value as numeric(9, 4)) as rate_pct,
    obs_status,
    load_id,
    extracted_at
from latest
