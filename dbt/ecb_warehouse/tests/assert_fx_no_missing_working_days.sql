{{ config(severity='warn') }}

-- Spec §7 (warn): no missing ECB working day for active currencies. Expected days = TARGET business days
-- (calendar, ADR 0004) between the first and last loaded FX date; a row = a currency/day without a rate.
with bounds as (
    select
        min(full_date) as first_date,
        max(full_date) as last_date
    from {{ ref('fct_fx_rate_daily') }}
),

expected as (
    select
        c.currency_code,
        d.full_date
    from {{ ref('dim_date') }} as d
    cross join bounds as b
    cross join {{ ref('dim_currency') }} as c
    where
        d.full_date between b.first_date and b.last_date
        and d.is_target_business_day
        and c.is_current
        and c.status = 'active'
)

select
    e.currency_code,
    e.full_date
from expected as e
left join {{ ref('fct_fx_rate_daily') }} as f
    on e.currency_code = f.currency_code and e.full_date = f.full_date
where f.full_date is null
