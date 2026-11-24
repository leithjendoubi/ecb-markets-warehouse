-- Row count + checksum of every raw table (proves that re-runs and backfills add no duplicates).
with raw_rows as (
    select
        'est' as tbl,
        load_id,
        row_num,
        obs_value
    from raw.est
    union all
    select
        'exr' as tbl,
        load_id,
        row_num,
        obs_value
    from raw.exr
    union all
    select
        'fm' as tbl,
        load_id,
        row_num,
        obs_value
    from raw.fm
    union all
    select
        'hicp' as tbl,
        load_id,
        row_num,
        obs_value
    from raw.hicp
)

select
    tbl,
    count(*) as n,
    md5(string_agg(load_id || row_num || coalesce(obs_value, ''), ',' order by load_id, row_num)) as checksum
from raw_rows
group by tbl
order by tbl;
