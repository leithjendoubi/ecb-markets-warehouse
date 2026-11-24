-- Use the configured schema name as-is (staging, marts, ...) instead of dbt's default "<target>_<custom>".
-- DBT_SCHEMA_PREFIX (default empty) lets tests build into throwaway schemas, e.g. it_scd2_marts.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set prefix = env_var('DBT_SCHEMA_PREFIX', '') -%}
    {%- if custom_schema_name is none -%}
        {{ prefix }}{{ target.schema }}
    {%- else -%}
        {{ prefix }}{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
