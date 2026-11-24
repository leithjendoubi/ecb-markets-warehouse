-- Pipeline run log (FR-09). One row per load attempt (dataset = exr|est|fm|hicp) and one row per fully
-- successful DAG run (dataset = 'all', mode = 'dag_run'), written by the last DAG task.
-- Idempotent: safe to re-run (make migrate).
create table if not exists ops.pipeline_runs (
    run_pk bigint generated always as identity primary key,
    dataset text not null,
    load_id text not null,
    mode text not null,
    dag_run_id text,
    rows_extracted integer not null default 0,
    rows_loaded integer not null default 0,
    started_at timestamptz not null,
    finished_at timestamptz not null,
    status text not null,
    error text,
    s3_key text,
    source_url text,
    constraint pipeline_runs_status_chk check (status in ('success', 'no_data', 'failed')),
    constraint pipeline_runs_mode_chk check (mode in ('full', 'incremental', 'backfill', 'dag_run'))
);

create index if not exists pipeline_runs_dataset_started_idx on ops.pipeline_runs (dataset, started_at);
create index if not exists pipeline_runs_load_id_idx on ops.pipeline_runs (load_id);
