# Runbook

Operational notes for the local stack. Spec: `docs/spec.md`.

## Prerequisites
- Docker Desktop (WSL2 backend). Seven long-running containers incl. Metabase (JVM capped by `JAVA_OPTS=-Xmx1g`);
  check actual memory use with `make stats`.
- GNU make: `scoop install make` (or `winget install GnuWin32.Make`); Python 3.12 for host-side tests.

## Start / stop
| Task | Command |
|---|---|
| First time | `cp .env.example .env` then `make venv` |
| Start everything, wait until healthy | `make up` |
| Status | `make ps` |
| Follow logs | `make logs` |
| Stop (keep data) | `make down` |
| Stop and DELETE all data volumes | `make clean` |
| SQL shell on the warehouse | `make psql` |
| Re-apply warehouse DDL | `make migrate` |

## Services and ports
| Service | URL | Login |
|---|---|---|
| Airflow 3 API server / UI | http://localhost:8080 | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` from `.env` |
| Metabase | http://localhost:3000 | created on first visit |
| SeaweedFS S3 API | http://localhost:8333 | `S3_ACCESS_KEY` / `S3_SECRET_KEY` from `.env` |
| PostgreSQL 16 | localhost:5432 | `WAREHOUSE_USER` / `WAREHOUSE_PASSWORD` (db `warehouse`) |

One Postgres instance holds three databases: `airflow` (Airflow metadata), `metabase` (Metabase app DB)
and `warehouse` (schemas `raw`, `ops`, `staging`, `intermediate`, `marts`, `snapshots`).
Metabase connects to `warehouse` as the read-only user `WAREHOUSE_RO_USER`, which can only read `marts`.

## How the pieces start
1. `postgres` runs `sql/init/00_init.sh` once on an empty volume (roles, databases, DDL from `sql/init/ddl`).
   Its healthcheck uses TCP so it only turns healthy after init has finished.
2. `seaweedfs` renders `infra/s3.json` (a template with placeholders) using `S3_ACCESS_KEY`/`S3_SECRET_KEY`.
3. `airflow-init` builds the Airflow image (`airflow/Dockerfile`), migrates the Airflow DB, creates the admin
   user and the S3 bucket (`python -m ecb_ingest.cli ensure-bucket`), then exits 0.
4. Airflow api-server, scheduler (LocalExecutor, runs the tasks), dag-processor and triggerer start; Metabase starts.

## Troubleshooting
- **Port already in use**: change `WAREHOUSE_PORT`, `AIRFLOW_PORT`, `METABASE_PORT` or `S3_PORT` in `.env`.
- **Changed a password in `.env` after first start**: Postgres roles were created with the old values.
  Either `make clean` (deletes data) or `alter role ... password ...` via `make psql`.
- **Changed pinned Python deps**: `make up` rebuilds the Airflow image. Code changes in `ingestion/`, `dbt/` and
  `airflow/dags/` are bind-mounted and need no rebuild.
- **S3 smoke test**: `make test-integration` (boto3 upload/read/delete against :8333).

## Data operations
| Task | Command |
|---|---|
| Normal run now | `make trigger` |
| Backfill a range (watermarks untouched) | `make backfill START=2024-01-01 END=2024-12-31` |
| Rebuild all dbt models from raw | `docker compose exec airflow-scheduler bash -c "cd /opt/project/dbt/ecb_warehouse && /opt/pipeline-venv/bin/dbt build --full-refresh"` |
| Idempotency proof | `make checksum` (spec query) |
| Docs + lineage check | `make docs-check` |
| Run-time statistics | `make benchmark` (from ops.pipeline_runs) |

- A revision older than the 7-day look-back is only picked up by a full refresh (ADR 0008).
- To version a currency (SCD2): edit `dbt/ecb_warehouse/seeds/currency_reference.csv`; the next DAG run
  (`dbt build` = seed + snapshot + models) creates the new version (ADR 0006).
- To restart incremental extraction from scratch for one dataset, remove its entry from
  `s3://$S3_BUCKET/_state/watermarks.json`; the next run is a full load.

## Dashboard
- `make dashboard`: creates the Metabase admin (`METABASE_ADMIN_EMAIL`/`_PASSWORD`) on first run, connects
  Metabase to the warehouse as the read-only user (schema `marts` only), and creates/updates every card in
  `docs/dashboard.md` plus the dashboard "ECB Markets Warehouse". Each card's query is executed once; a SQL
  error fails the command.
- `make dashboard-screenshot`: enables Metabase public sharing (local instance only) and renders the dashboard
  to `docs/img/dashboard.png` with headless Chrome/Edge in a throwaway profile.

## CI
`.github/workflows/ci.yml` has three jobs: `lint-unit` (ruff, sqlfluff, offline unit tests), `integration-dbt`
(Postgres 16 initialised by `sql/init`, integration tests, real fixtures loaded through extract+load,
`dbt build`, docs check, full refresh == incremental) and `dag` (builds the Airflow image, DAG tests).
The integration logic lives in `scripts/ci/*.sh` so it can be run the same way locally:

```bash
bash scripts/ci/start_postgres.sh ci-pg "" 5439          # throwaway Postgres on :5439
CI_WAREHOUSE_PORT=5439 PYTHON=.venv/Scripts/python bash scripts/ci/integration.sh   # (Linux: .venv/bin/python)
docker rm -f ci-pg
```
Tests marked `stack` (S3 smoke test) need the full compose stack and are not run in CI.

## pre-commit
`pre-commit install` once; hooks: whitespace/EOF/YAML/JSON, large files, private keys, ruff, sqlfluff, and a guard
that refuses to commit `.env`. `tests/fixtures/` is excluded (real API responses are kept byte-for-byte).
