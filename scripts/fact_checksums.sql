-- Row count + checksum of every fact table (full refresh vs incremental proof, spec §7).
-- fct_fx_rate_daily uses the exact spec query in scripts/checksum.sql; this adds every computed column.
with fx as (
    select
        'fct_fx_rate_daily' as model_name,
        count(*) as n,
        md5(string_agg(
            concat_ws('|', currency_sk, currency_code, full_date, rate_per_eur, daily_return_pct, vol_30d_pct),
            ',' order by currency_code, full_date
        )) as checksum
    from marts.fct_fx_rate_daily
),

policy as (
    select
        'fct_policy_rate_daily' as model_name,
        count(*) as n,
        md5(string_agg(
            concat_ws('|', full_date, dfr_pct, mro_pct, mlf_pct, is_dfr_filled, is_change_day),
            ',' order by full_date
        )) as checksum
    from marts.fct_policy_rate_daily
),

estr as (
    select
        'fct_estr_daily' as model_name,
        count(*) as n,
        md5(string_agg(concat_ws('|', full_date, estr_pct, total_volume_eur_mn), ',' order by full_date)) as checksum
    from marts.fct_estr_daily
),

hicp as (
    select
        'fct_inflation_monthly' as model_name,
        count(*) as n,
        md5(string_agg(
            concat_ws('|', month_start, hicp_yoy_pct, hicp_yoy_change_pp), ',' order by month_start
        )) as checksum
    from marts.fct_inflation_monthly
)

select * from fx
union all
select * from policy
union all
select * from estr
union all
select * from hicp
order by model_name;
