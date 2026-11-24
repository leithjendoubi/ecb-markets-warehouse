-- Grain: month (Q2, Q3). Average EUR STR over the month's publication days, key rates on the last available
-- day of the month, HICP YoY, and real rates = nominal minus HICP YoY. Rates are averaged, never summed.
with policy_daily as (
    select
        cast(date_trunc('month', full_date) as date) as month_start,
        full_date,
        dfr_pct,
        mro_pct,
        mlf_pct,
        is_change_day
    from {{ ref('fct_policy_rate_daily') }}
),

estr_daily as (
    select
        cast(date_trunc('month', full_date) as date) as month_start,
        estr_pct
    from {{ ref('fct_estr_daily') }}
),

months as (
    select distinct d.month_start
    from {{ ref('dim_date') }} as d
    where
        d.month_start >= date '1999-01-01'
        and d.month_start <= (select max(p.full_date) from policy_daily as p)
),

estr as (
    select
        month_start,
        round(avg(estr_pct), 4) as avg_estr_pct,
        count(*) as estr_days
    from estr_daily
    group by month_start
),

policy_month_end as (
    select distinct on (month_start)
        month_start,
        full_date as policy_as_of_date,
        dfr_pct,
        mro_pct,
        mlf_pct
    from policy_daily
    order by month_start asc, full_date desc
),

policy_changes as (
    select
        month_start,
        count(*) filter (where is_change_day) as policy_change_days
    from policy_daily
    group by month_start
)

select
    cast(to_char(m.month_start, 'YYYYMM') as integer) as month_key,
    m.month_start,
    e.avg_estr_pct,
    e.estr_days,
    p.policy_as_of_date,
    p.dfr_pct as dfr_month_end_pct,
    p.mro_pct as mro_month_end_pct,
    p.mlf_pct as mlf_month_end_pct,
    coalesce(c.policy_change_days, 0) as policy_change_days,
    i.hicp_yoy_pct,
    e.avg_estr_pct - i.hicp_yoy_pct as real_estr_pct,
    p.dfr_pct - i.hicp_yoy_pct as real_dfr_pct
from months as m
left join estr as e on m.month_start = e.month_start
left join policy_month_end as p on m.month_start = p.month_start
left join policy_changes as c on m.month_start = c.month_start
left join {{ ref('fct_inflation_monthly') }} as i on m.month_start = i.month_start
