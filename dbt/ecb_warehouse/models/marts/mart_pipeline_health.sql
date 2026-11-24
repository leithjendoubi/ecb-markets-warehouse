-- Grain: dataset x run date (Europe/Berlin) (Q4: is today's data complete and fresh?). Metabase reads marts
-- only, so the run log and the newest observation per dataset are exposed here.
with runs as (
    select
        dataset,
        run_date_berlin,
        count(*) as load_attempts,
        count(*) filter (where status = 'success') as successful_loads,
        count(*) filter (where status = 'no_data') as no_data_loads,
        count(*) filter (where status = 'failed') as failed_loads,
        coalesce(sum(rows_loaded) filter (where status <> 'failed'), 0) as rows_loaded,
        max(finished_at) as last_finished_at,
        round(max(duration_seconds)::numeric, 1) as max_duration_seconds
    from {{ ref('stg_ops__pipeline_runs') }}
    where dataset <> 'all'
    group by 1, 2
),

latest_obs as (
    select
        'exr' as dataset,
        max(full_date) as latest_observation
    from {{ ref('fct_fx_rate_daily') }}
    union all
    select
        'est' as dataset,
        max(full_date) as latest_observation
    from {{ ref('fct_estr_daily') }}
    union all
    select
        'fm' as dataset,
        max(full_date) as latest_observation
    from {{ ref('fct_policy_rate_daily') }}
    union all
    select
        'hicp' as dataset,
        max(month_start) as latest_observation
    from {{ ref('fct_inflation_monthly') }}
)

select
    r.dataset,
    r.run_date_berlin,
    r.load_attempts,
    r.successful_loads,
    r.no_data_loads,
    r.failed_loads,
    r.rows_loaded,
    r.last_finished_at,
    r.max_duration_seconds,
    o.latest_observation
from runs as r
left join latest_obs as o on r.dataset = o.dataset
