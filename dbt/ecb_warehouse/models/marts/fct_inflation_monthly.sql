{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='month_start',
        on_schema_change='fail'
    )
}}

-- Grain: month. Euro-area HICP annual rate of change. Re-builds the last `hicp_lookback_months` months on
-- incremental runs (flash estimates get revised); reads one extra month for the month-on-month change.
with hicp as (
    select
        month_start,
        hicp_yoy_pct
    from {{ ref('stg_ecb__hicp') }}
    {% if is_incremental() %}
        where month_start >= (
            select max(t.month_start) - interval '1 month' * ({{ var('hicp_lookback_months') }} + 1)
            from {{ this }} as t
        )
    {% endif %}
),

with_change as (
    select
        month_start,
        hicp_yoy_pct,
        hicp_yoy_pct - lag(hicp_yoy_pct) over (order by month_start) as hicp_yoy_change_pp
    from hicp
)

select
    d.date_key as month_start_date_key,
    w.month_start,
    cast(to_char(w.month_start, 'YYYYMM') as integer) as month_key,
    w.hicp_yoy_pct,
    w.hicp_yoy_change_pp
from with_change as w
inner join {{ ref('dim_date') }} as d on w.month_start = d.full_date
{% if is_incremental() %}
    where w.month_start >= (
        select max(t.month_start) - interval '1 month' * {{ var('hicp_lookback_months') }}
        from {{ this }} as t
    )
{% endif %}
