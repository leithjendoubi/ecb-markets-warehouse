-- Idempotency proof (spec §7): identical output before and after a re-run / backfill / full refresh.
select
    count(*) as n,
    md5(
        string_agg(
            c.currency_code || f.full_date || f.rate_per_eur, ','
            order by c.currency_code, f.full_date
        )
    ) as checksum
from marts.fct_fx_rate_daily as f
inner join marts.dim_currency as c on f.currency_sk = c.currency_sk;
