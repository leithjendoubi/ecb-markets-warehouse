-- Spec §7 (error): exactly one is_current row per currency that is still in the seed.
with seeded as (
    select currency_code
    from {{ ref('currency_reference') }}
),

current_rows as (
    select
        currency_code,
        count(*) filter (where is_current) as n_current
    from {{ ref('dim_currency') }}
    group by currency_code
)

select
    s.currency_code,
    coalesce(c.n_current, 0) as n_current
from seeded as s
left join current_rows as c on s.currency_code = c.currency_code
where coalesce(c.n_current, 0) <> 1
