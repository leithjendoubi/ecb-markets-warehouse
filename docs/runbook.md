# Runbook

Operational notes for the local stack. Spec: `docs/spec.md`.

## Prerequisites
- Docker Desktop (WSL2 backend) with at least 6 GB memory for the VM. Metabase alone uses ~1.5 GB.
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
