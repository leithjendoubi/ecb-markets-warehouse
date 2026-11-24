#!/usr/bin/env bash
# Runs once, on an empty data volume (docker-entrypoint-initdb.d).
# Creates roles + databases, then applies the warehouse DDL in sql/init/ddl/ (idempotent; `make migrate` reruns it).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
create role airflow login password '${AIRFLOW_DB_PASSWORD}';
create database airflow owner airflow;
create role metabase login password '${METABASE_DB_PASSWORD}';
create database metabase owner metabase;
create role ${WAREHOUSE_USER} login password '${WAREHOUSE_PASSWORD}';
create database ${WAREHOUSE_DB} owner ${WAREHOUSE_USER};
create role ${WAREHOUSE_RO_USER} login password '${WAREHOUSE_RO_PASSWORD}';
SQL

bash /docker-entrypoint-initdb.d/ddl/apply_ddl.sh
