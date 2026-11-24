{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='full_date',
        on_schema_change='fail'
    )
}}

-- Grain: calendar day, from the first to the last FM observation. DFR / MRO / MLF forward-filled onto the
-- date spine, but never across more than `max_ffill_days` days without an observation (ADR 0007): the MRO
-- fixed-rate series does not exist 2000-06-28..2008-10-14 and must stay NULL there.
with bounds as (
    select
        min(rate_date) as first_date,
        max(rate_date) as last_date
    from {{ ref('int_policy_rates_pivoted') }}
),

spine as (
    select
        d.date_key,
        d.full_date
    from {{ ref('dim_date') }} as d
    cross join bounds as b
    where
        d.full_date between b.first_date and b.last_date
        {% if is_incremental() %}
            and d.full_date >= (
                select max(t.full_date) - {{ var('lookback_days') }} - {{ var('window_buffer_days') }}
                from {{ this }} as t
            )
        {% endif %}
),

observed as (
    select
        s.date_key,
        s.full_date,
        p.dfr_pct,
        p.mro_pct,
        p.mlf_pct
    from spine as s
    left join {{ ref('int_policy_rates_pivoted') }} as p on s.full_date = p.rate_date
),

grouped as (
    select
        date_key,
        full_date,
        dfr_pct,
        mro_pct,
        mlf_pct,
        count(dfr_pct) over (order by full_date) as dfr_grp,
        count(mro_pct) over (order by full_date) as mro_grp,
        count(mlf_pct) over (order by full_date) as mlf_grp
    from observed
),

filled as (
    select
        date_key,
        full_date,
        dfr_pct is null as is_dfr_filled,
        max(dfr_pct) over (partition by dfr_grp) as dfr_last,
        min(full_date) over (partition by dfr_grp) as dfr_last_date,
        max(mro_pct) over (partition by mro_grp) as mro_last,
        min(full_date) over (partition by mro_grp) as mro_last_date,
        max(mlf_pct) over (partition by mlf_grp) as mlf_last,
        min(full_date) over (partition by mlf_grp) as mlf_last_date
    from grouped
),

limited as (
    select
        date_key,
        full_date,
        is_dfr_filled,
        case when full_date - dfr_last_date <= {{ var('max_ffill_days') }} then dfr_last end as dfr_pct,
        case when full_date - mro_last_date <= {{ var('max_ffill_days') }} then mro_last end as mro_pct,
        case when full_date - mlf_last_date <= {{ var('max_ffill_days') }} then mlf_last end as mlf_pct
    from filled
),

changes as (
    select
        date_key,
        full_date,
        dfr_pct,
        mro_pct,
        mlf_pct,
        is_dfr_filled,
        lag(full_date) over (order by full_date) as prev_date,
        lag(dfr_pct) over (order by full_date) as prev_dfr_pct,
        lag(mro_pct) over (order by full_date) as prev_mro_pct,
        lag(mlf_pct) over (order by full_date) as prev_mlf_pct
    from limited
)

select
    date_key,
    full_date,
    dfr_pct,
    mro_pct,
    mlf_pct,
    is_dfr_filled,
    coalesce(
        prev_date is not null
        and (
            dfr_pct is distinct from prev_dfr_pct
            or mro_pct is distinct from prev_mro_pct
            or mlf_pct is distinct from prev_mlf_pct
        ),
        false
    ) as is_change_day
from changes
{% if is_incremental() %}
    where full_date >= (select max(t.full_date) - {{ var('lookback_days') }} from {{ this }} as t)
{% endif %}
