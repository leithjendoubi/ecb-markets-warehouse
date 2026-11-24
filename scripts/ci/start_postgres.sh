#!/usr/bin/env bash
# Start a throwaway Postgres 16 initialised by the same sql/init scripts as the compose stack.
# Usage: scripts/ci/start_postgres.sh <container-name> [docker-network] [host-port]
# Env values come from .env.example (non-secret local defaults), so CI also proves .env.example is complete.
set -euo pipefail
name="${1:?container name}"; network="${2:-}"; port="${3:-5432}"
src="$(pwd -W 2>/dev/null || pwd)"   # Git Bash on Windows needs a Windows path for -v
set -a; source .env.example; set +a
net_args=(); [[ -n "$network" ]] && net_args=(--network "$network")
docker rm -f "$name" >/dev/null 2>&1 || true
MSYS_NO_PATHCONV=1 docker run -d --name "$name" "${net_args[@]}" -p "$port:5432" \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD="$POSTGRES_SUPERUSER_PASSWORD" -e POSTGRES_DB=postgres \
  -e AIRFLOW_DB_PASSWORD -e METABASE_DB_PASSWORD -e WAREHOUSE_DB -e WAREHOUSE_USER -e WAREHOUSE_PASSWORD \
  -e WAREHOUSE_RO_USER -e WAREHOUSE_RO_PASSWORD \
  -v "$src/sql/init:/docker-entrypoint-initdb.d:ro" postgres:16.16 >/dev/null
for _ in $(seq 1 60); do
  if MSYS_NO_PATHCONV=1 docker exec "$name" sh -c "pg_isready -q -h 127.0.0.1 -U postgres && psql -h 127.0.0.1 -U postgres -d $WAREHOUSE_DB -tAc \"select 1 from pg_namespace where nspname='ops'\" | grep -q 1"; then
    echo "postgres $name ready"; exit 0
  fi
  sleep 2
done
docker logs "$name" | tail -30; echo "postgres $name did not become ready" >&2; exit 1
