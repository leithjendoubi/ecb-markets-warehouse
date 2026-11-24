-- Run-time statistics, computed only from ops.pipeline_runs (no invented numbers).
-- A "daily run" = one fully successful incremental DAG run (dataset = 'all' row written by the last task),
-- measured from DAG start to the end of dbt source freshness. Full loads and backfills are excluded.
with dag_runs as (
    select
        r.load_id as dag_run_id,
        r.started_at,
        r.finished_at,
        r.rows_loaded,
        extract(epoch from r.finished_at - r.started_at) as seconds
    from ops.pipeline_runs as r
    where
        r.dataset = 'all'
        and r.status = 'success'
        and not exists (
            select 1
            from ops.pipeline_runs as d
            where d.dag_run_id = r.load_id and d.mode in ('full', 'backfill')
        )
),

last_five as (
    select *
    from dag_runs
    order by started_at desc
    limit 5
)

select
    count(*) as runs_measured,
    round(percentile_cont(0.5) within group (order by seconds)::numeric, 1) as median_seconds,
    round(min(seconds)::numeric, 1) as min_seconds,
    round(max(seconds)::numeric, 1) as max_seconds,
    min(started_at) as first_run_started,
    max(started_at) as last_run_started
from last_five;
