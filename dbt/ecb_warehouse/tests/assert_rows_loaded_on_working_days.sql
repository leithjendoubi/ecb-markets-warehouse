-- Spec §7 (error): rows loaded > 0 on working days. For every TARGET business day on which at least one
-- normal (full/incremental) EXR load ran after the 16:00 CET publication time, the EXR loads of that day
-- must have loaded rows. Earlier runs and backfills are ignored: before 16:00 "no data" is legitimate.
with exr_runs as (
    select
        run_date_berlin,
        rows_loaded,
        status,
        cast(started_at at time zone 'Europe/Berlin' as time) >= time '16:30' as after_publication
    from {{ ref('stg_ops__pipeline_runs') }}
    where
        dataset = 'exr'
        and mode in ('full', 'incremental')
        and status <> 'failed'
),

per_day as (
    select
        run_date_berlin,
        sum(rows_loaded) as rows_loaded,
        bool_or(after_publication) as had_run_after_publication
    from exr_runs
    group by run_date_berlin
)

select
    p.run_date_berlin,
    p.rows_loaded
from per_day as p
inner join {{ ref('dim_date') }} as d on p.run_date_berlin = d.full_date
where
    d.is_target_business_day
    and p.had_run_after_publication
    and p.rows_loaded = 0
