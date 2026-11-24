-- Row count + checksum of every raw table (used to prove re-runs and backfills add no duplicates).
select 'exr' as tbl, count(*) as n, md5(string_agg(load_id || row_num || coalesce(obs_value, ''), ',' order by load_id, row_num)) as checksum from raw.exr
union all
select 'est', count(*), md5(string_agg(load_id || row_num || coalesce(obs_value, ''), ',' order by load_id, row_num)) from raw.est
union all
select 'fm', count(*), md5(string_agg(load_id || row_num || coalesce(obs_value, ''), ',' order by load_id, row_num)) from raw.fm
union all
select 'hicp', count(*), md5(string_agg(load_id || row_num || coalesce(obs_value, ''), ',' order by load_id, row_num)) from raw.hicp
order by tbl;
