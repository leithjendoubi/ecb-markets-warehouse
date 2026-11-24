-- Grain: currency x month (Q1). Rates are foreign currency per 1 EUR: a positive change means the euro
-- strengthened against that currency. MTD = vs previous month-end, YTD = vs previous year-end.
-- Rates are averaged / compared, never summed.
with monthly as (
    select
        currency_code,
        cast(date_trunc('month', full_date) as date) as month_start,
        min(full_date) as first_rate_date,
        max(full_date) as last_rate_date,
        count(*) as rate_days,
        round(avg(rate_per_eur), 6) as avg_rate_per_eur,
        min(rate_per_eur) as min_rate_per_eur,
        max(rate_per_eur) as max_rate_per_eur
    from {{ ref('fct_fx_rate_daily') }}
    group by 1, 2
),

month_end as (
    select
        m.currency_code,
        m.month_start,
        m.first_rate_date,
        m.last_rate_date,
        m.rate_days,
        m.avg_rate_per_eur,
        m.min_rate_per_eur,
        m.max_rate_per_eur,
        f.rate_per_eur as month_end_rate_per_eur,
        f.vol_30d_pct as month_end_vol_30d_pct
    from monthly as m
    inner join {{ ref('fct_fx_rate_daily') }} as f
        on m.currency_code = f.currency_code and m.last_rate_date = f.full_date
),

with_refs as (
    select
        currency_code,
        month_start,
        first_rate_date,
        last_rate_date,
        rate_days,
        avg_rate_per_eur,
        min_rate_per_eur,
        max_rate_per_eur,
        month_end_rate_per_eur,
        month_end_vol_30d_pct,
        lag(month_end_rate_per_eur) over (partition by currency_code order by month_start) as prev_month_end_rate,
        lag(month_start) over (partition by currency_code order by month_start) as prev_month_start
    from month_end
),

year_end as (
    select
        currency_code,
        cast(extract(year from month_start) as integer) as year_number,
        month_end_rate_per_eur as year_end_rate
    from month_end
    where extract(month from month_start) = 12
)

select
    r.currency_code,
    c.currency_name,
    r.month_start,
    cast(to_char(r.month_start, 'YYYYMM') as integer) as month_key,
    r.first_rate_date,
    r.last_rate_date,
    r.rate_days,
    r.avg_rate_per_eur,
    r.min_rate_per_eur,
    r.max_rate_per_eur,
    r.month_end_rate_per_eur,
    case
        when r.prev_month_start = cast(r.month_start - interval '1 month' as date)
            then round((r.month_end_rate_per_eur / r.prev_month_end_rate - 1) * 100, 4)
    end as mtd_change_pct,
    round((r.month_end_rate_per_eur / y.year_end_rate - 1) * 100, 4) as ytd_change_pct,
    r.month_end_vol_30d_pct
from with_refs as r
left join year_end as y
    on
        r.currency_code = y.currency_code
        and cast(extract(year from r.month_start) as integer) = y.year_number + 1
left join {{ ref('dim_currency') }} as c
    on r.currency_code = c.currency_code and c.is_current
