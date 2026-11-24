-- Euro short-term rate (EUR STR): WT = rate in percent, TT = total volume in EUR millions (UNIT_MULT 6).
with latest as (
    {{ latest_observation(source('raw', 'est')) }}
)

select
    series_key,
    time_period,
    data_type_est as measure_code,
    cast(time_period as date) as obs_date,
    cast(obs_value as numeric(18, 6)) as obs_value,
    unit_measure,
    cast(unit_mult as integer) as unit_mult,
    obs_status,
    load_id,
    extracted_at
from latest
