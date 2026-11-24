# Metabase dashboard: "ECB Markets Warehouse"

FR-10. One dashboard answering Q1-Q4 (spec §2). Every card is a native SQL question on the `marts` schema,
run by the read-only user `WAREHOUSE_RO_USER` (it cannot read `raw`, `staging` or `ops`).

This file is the **single source** of the dashboard: `scripts/metabase_setup.py` (`make dashboard`) parses each
`###` card below (its `card:` settings comment and its SQL block) and creates or updates the questions and the
dashboard through the Metabase API. Edit the SQL here, then re-run `make dashboard`.

Screenshot: `docs/img/dashboard.png` (`make dashboard-screenshot`).

Reading guide: FX rates are foreign currency per 1 EUR, so a positive change means the euro strengthened.
Rates are averaged or compared, never summed.

## Q1: How have major currencies moved vs the euro, and how volatile are they?

### Q1.1 Euro vs major currencies: month-to-date and year-to-date change (%)
<!-- card: display=bar x=currency_code y=ytd_change_pct,mtd_change_pct row=0 col=0 w=12 h=6 -->
```sql
select
    currency_code,
    ytd_change_pct,
    mtd_change_pct
from marts.mart_fx_performance
where month_start = (select max(m.month_start) from marts.mart_fx_performance as m)
order by ytd_change_pct desc
```

### Q1.2 EUR/USD, EUR/GBP, EUR/CHF daily reference rates, last 2 years
<!-- card: display=line x=full_date y=usd,gbp,chf row=0 col=12 w=12 h=6 -->
```sql
select
    full_date,
    max(rate_per_eur) filter (where currency_code = 'USD') as usd,
    max(rate_per_eur) filter (where currency_code = 'GBP') as gbp,
    max(rate_per_eur) filter (where currency_code = 'CHF') as chf
from marts.fct_fx_rate_daily
where full_date >= (select max(f.full_date) - interval '2 years' from marts.fct_fx_rate_daily as f)
group by full_date
order by full_date
```

### Q1.3 Latest rates and 30-day volatility
<!-- card: display=table row=6 col=0 w=12 h=7 -->
```sql
select
    c.currency_name,
    f.currency_code,
    f.full_date as rate_date,
    f.rate_per_eur,
    f.daily_return_pct,
    f.vol_30d_pct
from marts.fct_fx_rate_daily as f
inner join marts.dim_currency as c on f.currency_sk = c.currency_sk
where f.full_date = (select max(m.full_date) from marts.fct_fx_rate_daily as m)
order by f.vol_30d_pct desc
```

## Q2: How do ECB policy-rate decisions line up with EUR STR and FX moves?

### Q2.1 ECB key rates (week end) and EUR STR (weekly average) since 2019-10 (%)
<!-- card: display=line x=week_start y=dfr_pct,mro_pct,mlf_pct,avg_estr_pct row=6 col=12 w=12 h=7 -->
```sql
-- Weekly, not daily: Metabase shows at most 2,000 rows per question.
select
    cast(date_trunc('week', p.full_date) as date) as week_start,
    (array_agg(p.dfr_pct order by p.full_date desc))[1] as dfr_pct,
    (array_agg(p.mro_pct order by p.full_date desc))[1] as mro_pct,
    (array_agg(p.mlf_pct order by p.full_date desc))[1] as mlf_pct,
    round(avg(e.estr_pct), 3) as avg_estr_pct
from marts.fct_policy_rate_daily as p
left join marts.fct_estr_daily as e on p.full_date = e.full_date
where p.full_date >= date '2019-10-01'
group by cast(date_trunc('week', p.full_date) as date)
order by week_start
```

### Q2.2 Each key-rate change: EUR STR before/after and EUR/USD 5 working days later
<!-- card: display=table row=13 col=0 w=24 h=6 -->
```sql
with changes as (
    select
        full_date,
        dfr_pct,
        lag(dfr_pct) over (order by full_date) as dfr_before,
        is_change_day
    from marts.fct_policy_rate_daily
)

select
    c.full_date as change_date,
    c.dfr_before,
    c.dfr_pct as dfr_after,
    (
        select e.estr_pct from marts.fct_estr_daily as e
        where e.full_date < c.full_date order by e.full_date desc limit 1
    ) as estr_before,
    (
        select e.estr_pct from marts.fct_estr_daily as e
        where e.full_date >= c.full_date order by e.full_date offset 4 limit 1
    ) as estr_after_5d,
    round((
        (
            select f.rate_per_eur from marts.fct_fx_rate_daily as f
            where f.currency_code = 'USD' and f.full_date >= c.full_date order by f.full_date offset 4 limit 1
        ) / (
            select f.rate_per_eur from marts.fct_fx_rate_daily as f
            where f.currency_code = 'USD' and f.full_date < c.full_date order by f.full_date desc limit 1
        ) - 1
    ) * 100, 3) as eurusd_change_5d_pct
from changes as c
where c.is_change_day and c.full_date >= date '2019-10-01'
order by c.full_date desc
```

## Q3: What is euro-area inflation doing; what is the real EUR STR?

### Q3.1 HICP inflation, EUR STR and real EUR STR, monthly since 2015 (%)
<!-- card: display=line x=month_start y=hicp_yoy_pct,avg_estr_pct,real_estr_pct,dfr_month_end_pct row=19 col=0 w=16 h=7 -->
```sql
select
    month_start,
    hicp_yoy_pct,
    avg_estr_pct,
    real_estr_pct,
    dfr_month_end_pct
from marts.mart_rates_monthly
where month_start >= date '2015-01-01'
order by month_start
```

### Q3.2 Latest month
<!-- card: display=table row=19 col=16 w=8 h=7 -->
```sql
select
    month_start,
    hicp_yoy_pct,
    avg_estr_pct,
    real_estr_pct,
    real_dfr_pct
from marts.mart_rates_monthly
where hicp_yoy_pct is not null
order by month_start desc
limit 6
```

## Q4: Is today's data complete and fresh?

### Q4.1 Hours since the newest ECB reference rate was published
<!-- card: display=scalar row=26 col=0 w=6 h=6 -->
```sql
select
    round(
        cast(extract(epoch from now() - ((max(full_date) + time '16:00') at time zone 'Europe/Berlin')) / 3600 as numeric),
        1
    ) as hours_since_latest_rate
from marts.fct_fx_rate_daily
```

### Q4.2 Pipeline health per dataset
<!-- card: display=table row=26 col=6 w=18 h=6 -->
```sql
select
    dataset,
    max(latest_observation) as latest_observation,
    max(last_finished_at) as last_load_finished_at,
    coalesce(sum(rows_loaded) filter (where run_date_berlin = current_date), 0) as rows_loaded_today,
    coalesce(sum(failed_loads) filter (where run_date_berlin >= current_date - 7), 0) as failed_loads_7d
from marts.mart_pipeline_health
group by dataset
order by dataset
```
