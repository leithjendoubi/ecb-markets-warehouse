#!/usr/bin/env bash
# CI integration stage (also runnable locally, see docs/runbook.md). Expects a Postgres started by
# scripts/ci/start_postgres.sh and WAREHOUSE_HOST/WAREHOUSE_PORT pointing at it.
# No live API calls: fixtures are served by a mock transport, S3 is an in-memory fake.
set -euo pipefail
set -a; source .env.example; set +a
export WAREHOUSE_HOST="${CI_WAREHOUSE_HOST:-localhost}" WAREHOUSE_PORT="${CI_WAREHOUSE_PORT:-5432}"
export DBT_PROFILES_DIR=dbt/ecb_warehouse DBT_TARGET_PATH="${DBT_TARGET_PATH:-/tmp/dbt-target}" \
       DBT_LOG_PATH="${DBT_LOG_PATH:-/tmp/dbt-logs}" DBT_SEND_ANONYMOUS_USAGE_STATS=false
PY="${PYTHON:-python}"
DBT=(dbt --no-use-colors)
P=dbt/ecb_warehouse

echo "::group::pytest integration (loader idempotency, SCD2 snapshot)"
"$PY" -m pytest -m "integration and not stack" -q
echo "::endgroup::"

echo "::group::load real ECB fixtures into raw.* (extract -> fake S3 -> load)"
"$PY" scripts/ci/load_fixtures.py
echo "::endgroup::"

echo "::group::dbt build (seed, snapshot, models, all tests)"
"${DBT[@]}" build --project-dir "$P"
echo "::endgroup::"

echo "::group::docs + lineage check"
"${DBT[@]}" docs generate --project-dir "$P" --quiet
"$PY" scripts/check_dbt_docs.py "$DBT_TARGET_PATH"
echo "::endgroup::"

echo "::group::full refresh == incremental (spec §7)"
q() { "$PY" scripts/ci/fact_checksums.py; }
before="$(q)"
"${DBT[@]}" build --project-dir "$P" --full-refresh --quiet
after="$(q)"
echo "$before"
if [[ "$before" != "$after" ]]; then echo "checksums differ after full refresh:"; echo "$after"; exit 1; fi
echo "checksums identical"
echo "::endgroup::"
