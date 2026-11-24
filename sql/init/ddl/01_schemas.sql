-- Warehouse schemas. Idempotent: safe to re-run (make migrate).
-- raw: loader output, one table per dataset. ops: run log + pipeline metadata.
-- staging / intermediate / marts: built by dbt.
create schema if not exists raw;
create schema if not exists ops;
create schema if not exists staging;
create schema if not exists intermediate;
create schema if not exists marts;
create schema if not exists snapshots;

-- Metabase reads marts only (read-only user).
grant connect on database :"dbname" to :"ro_user";
grant usage on schema marts to :"ro_user";
grant select on all tables in schema marts to :"ro_user";
alter default privileges for role :"owner" in schema marts grant select on tables to :"ro_user";
