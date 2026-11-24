-- ECB reference exchange rates: one row per (series_key, rate_date), latest version, typed.
with latest as (
    {{ latest_observation(source('raw', 'exr')) }}
)

select
    series_key,
    time_period,
    currency as currency_code,
    currency_denom as base_currency_code,
    cast(time_period as date) as rate_date,
    cast(obs_value as numeric(18, 6)) as rate_per_eur,
    obs_status,
    title as series_title,
    load_id,
    extracted_at
from latest
