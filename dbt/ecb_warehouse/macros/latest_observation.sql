{#
  Keep the latest version of each observation (FR-05). Raw keeps every load (incl. ECB revisions);
  the newest extraction wins, ties broken by ingestion time and load_id.
#}
{% macro latest_observation(source_relation) -%}
    select *
    from (
        select
            src.*,
            row_number() over (
                partition by src.series_key, src.time_period
                order by src.extracted_at desc, src.ingested_at desc, src.load_id desc
            ) as version_rank
        from {{ source_relation }} as src
        where src.obs_value is not null
    ) as ranked
    where ranked.version_rank = 1
{%- endmacro %}
