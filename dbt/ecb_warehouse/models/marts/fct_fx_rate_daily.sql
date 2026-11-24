{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['currency_code', 'full_date'],
        on_schema_change='fail'
    )
}}

-- Grain: currency x ECB working day. Rates are foreign currency per 1 EUR and non-additive (never sum).
-- Incremental: re-builds the last `lookback_days` days (ECB revisions); reads `window_buffer_days` more
-- history so the previous rate and the 30-day volatility match a full refresh exactly.
with rates as (
    select
        currency_code,
        rate_date as full_date,
        rate_per_eur
    from {{ ref('stg_ecb__exr') }}
    {% if is_incremental() %}
        where rate_date >= (
            select max(t.full_date) - {{ var('lookback_days') }} - {{ var('window_buffer_days') }}
            from {{ this }} as t
        )
    {% endif %}
),

with_returns as (
    select
        currency_code,
        full_date,
        rate_per_eur,
        lag(rate_per_eur) over (partition by currency_code order by full_date) as prev_rate_per_eur
    from rates
),

returns as (
    select
        currency_code,
        full_date,
        rate_per_eur,
        prev_rate_per_eur,
        round((rate_per_eur / prev_rate_per_eur - 1) * 100, 6) as daily_return_pct
    from with_returns
),

vol as (
    select
        currency_code,
        full_date,
        rate_per_eur,
        prev_rate_per_eur,
        daily_return_pct,
        stddev_samp(daily_return_pct) over w30 as vol_30d_raw,
        count(daily_return_pct) over w30 as n_returns_30d
    from returns
    window w30 as (partition by currency_code order by full_date rows between 29 preceding and current row)
)

select
    c.currency_sk,
    d.date_key,
    v.currency_code,
    v.full_date,
    v.rate_per_eur,
    v.prev_rate_per_eur,
    v.daily_return_pct,
    case when v.n_returns_30d = 30 then round(v.vol_30d_raw, 6) end as vol_30d_pct
from vol as v
inner join {{ ref('dim_date') }} as d on v.full_date = d.full_date
inner join {{ ref('dim_currency') }} as c
    on
        v.currency_code = c.currency_code
        and v.full_date >= c.valid_from
        and v.full_date < c.valid_to
{% if is_incremental() %}
    where v.full_date >= (select max(t.full_date) - {{ var('lookback_days') }} from {{ this }} as t)
{% endif %}
