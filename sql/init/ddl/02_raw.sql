-- Raw landing tables: one per dataset (ingestion/ecb_ingest/config.yaml), the configured API columns as text.
-- Typing and de-duplication happen in dbt staging. Generated from config.yaml; a unit test keeps them in sync.
-- Idempotent: safe to re-run (make migrate).

create table if not exists raw.exr (
    series_key text,
    freq text,
    currency text,
    currency_denom text,
    exr_type text,
    exr_suffix text,
    time_period text,
    obs_value text,
    obs_status text,
    obs_conf text,
    decimals text,
    unit text,
    unit_mult text,
    title text,
    load_id text not null,
    row_num integer not null,
    extracted_at timestamptz not null,
    ingested_at timestamptz not null default now(),
    source_url text not null,
    s3_key text not null,
    constraint exr_pk primary key (load_id, row_num)
);
create index if not exists exr_series_period_idx on raw.exr (series_key, time_period);

create table if not exists raw.est (
    series_key text,
    freq text,
    benchmark_item text,
    data_type_est text,
    time_period text,
    obs_value text,
    obs_status text,
    conf_status text,
    decimals text,
    unit_measure text,
    unit_mult text,
    title text,
    load_id text not null,
    row_num integer not null,
    extracted_at timestamptz not null,
    ingested_at timestamptz not null default now(),
    source_url text not null,
    s3_key text not null,
    constraint est_pk primary key (load_id, row_num)
);
create index if not exists est_series_period_idx on raw.est (series_key, time_period);

create table if not exists raw.fm (
    series_key text,
    freq text,
    ref_area text,
    currency text,
    provider_fm text,
    instrument_fm text,
    provider_fm_id text,
    data_type_fm text,
    time_period text,
    obs_value text,
    obs_status text,
    obs_conf text,
    decimals text,
    unit text,
    unit_mult text,
    title text,
    load_id text not null,
    row_num integer not null,
    extracted_at timestamptz not null,
    ingested_at timestamptz not null default now(),
    source_url text not null,
    s3_key text not null,
    constraint fm_pk primary key (load_id, row_num)
);
create index if not exists fm_series_period_idx on raw.fm (series_key, time_period);

create table if not exists raw.hicp (
    series_key text,
    freq text,
    ref_area text,
    adjustment text,
    icp_item text,
    data_provider text,
    icp_suffix text,
    time_period text,
    obs_value text,
    obs_status text,
    conf_status text,
    decimals text,
    unit text,
    unit_mult text,
    title text,
    load_id text not null,
    row_num integer not null,
    extracted_at timestamptz not null,
    ingested_at timestamptz not null default now(),
    source_url text not null,
    s3_key text not null,
    constraint hicp_pk primary key (load_id, row_num)
);
create index if not exists hicp_series_period_idx on raw.hicp (series_key, time_period);
