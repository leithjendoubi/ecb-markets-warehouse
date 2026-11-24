-- Pipeline run log, typed and with a duration column (Q4: is today's data complete and fresh?).
select
    run_pk,
    dataset,
    load_id,
    mode,
    dag_run_id,
    rows_extracted,
    rows_loaded,
    started_at,
    finished_at,
    status,
    error,
    cast(started_at at time zone 'Europe/Berlin' as date) as run_date_berlin,
    extract(epoch from finished_at - started_at) as duration_seconds
from {{ source('ops', 'pipeline_runs') }}
