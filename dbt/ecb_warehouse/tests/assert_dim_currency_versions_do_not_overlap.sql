-- SCD2 integrity: versions of one currency are contiguous and never overlap.
with ordered as (
    select
        currency_code,
        valid_from,
        valid_to,
        lead(valid_from) over (partition by currency_code order by valid_from) as next_valid_from
    from {{ ref('dim_currency') }}
)

select
    currency_code,
    valid_from,
    valid_to,
    next_valid_from
from ordered
where
    valid_to <= valid_from
    or (next_valid_from is not null and next_valid_from <> valid_to)
