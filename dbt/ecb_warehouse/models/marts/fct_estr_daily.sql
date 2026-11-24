{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='full_date',
        on_schema_change='fail'
    )
}}

-- Grain: TARGET business day with a published EUR STR (from 2019-10-01). Re-builds the last
-- `lookback_days` days on incremental runs (ECB revisions).
select
    d.date_key,
    e.obs_date as full_date,
    e.estr_pct,
    e.total_volume_eur_mn
from {{ ref('int_estr_pivoted') }} as e
inner join {{ ref('dim_date') }} as d on e.obs_date = d.full_date
{% if is_incremental() %}
    where e.obs_date >= (select max(t.full_date) - {{ var('lookback_days') }} from {{ this }} as t)
{% endif %}
