-- SCD Type 2 currency dimension built from the snapshot of seeds/currency_reference.csv (FR-07).
-- The first version of each currency is back-dated to 1999-01-01 so historical facts resolve to it;
-- later versions start when the snapshot detected the change. valid_to is exclusive.
with snap as (
    select
        dbt_scd_id,
        currency_code,
        currency_name,
        status,
        last_rate_date,
        notes,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('snap_currency') }}
),

versioned as (
    select
        dbt_scd_id,
        currency_code,
        currency_name,
        status,
        last_rate_date,
        notes,
        dbt_valid_from,
        dbt_valid_to,
        row_number() over (partition by currency_code order by dbt_valid_from) as version_number
    from snap
)

select
    dbt_scd_id as currency_sk,
    currency_code,
    currency_name,
    status,
    last_rate_date,
    notes,
    version_number,
    case
        when version_number = 1 then cast('1999-01-01' as timestamp)
        else dbt_valid_from
    end as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to = cast('9999-12-31' as timestamp) as is_current
from versioned
