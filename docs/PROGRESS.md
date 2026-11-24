# Progress log

One entry per milestone (spec §9). Numbers below come from commands run during the milestone.

## M1: Compose stack, Makefile, runbook, ECB fixtures (2026-11-24)
**Built**
- `docker-compose.yml`: Postgres 16.16, SeaweedFS 4.55 (S3 on :8333), Airflow 3.4.0 (python 3.12, LocalExecutor,
  FAB auth; api-server, scheduler, dag-processor, triggerer, init) and Metabase v0.64.8.4 (app DB in Postgres).
- `airflow/Dockerfile`: Airflow image plus an isolated `/opt/pipeline-venv` built from `pyproject.toml` pins (ingestion + dbt).
- `sql/init`: creates the `airflow`, `metabase` and `warehouse` databases, the owner and read-only roles,
  and the schemas raw/ops/staging/intermediate/marts/snapshots. Metabase's read-only user can read `marts` only.
- `infra/s3.json`: SeaweedFS identity template with placeholders, rendered from `.env` at start (no secrets in Git).
- `Makefile` (up/down/logs/psql/test/lint/dbt-build/backfill + extras), `.env.example`, `docs/runbook.md`.
- `ecb_ingest` skeleton: settings from env, S3 wrapper with write-once `put_immutable`, CLI `ensure-bucket`.
- `tests/fixtures/`: real ECB responses (body + headers) fetched 2026-11-24:
  `exr_sample` (10 currencies, 2024-12-20..2025-01-08), `est_sample` (WT+TT), `fm_sample` (DFR/MRR_FR/MLFR,
  2024-06-01..15), `hicp_sample` (2024-01..), `exr_hrk` (discontinued kuna), `exr_empty` (no-data response).

**Checks**
- `make up`: all 7 long-running services healthy, airflow-init exited 0, bucket `ecb-lake` created.
- Airflow `/api/v2/monitor/health` all components healthy; UI :8080 -> 200; `/auth/token` with admin -> 201.
- Metabase `/api/health` -> `{"status":"ok"}`; UI :3000 -> 200.
- `make test`: 4 passed (offline). `make test-integration`: boto3 upload/read/delete on :8333 passed.

**Findings from the real API (shape later milestones)**
- No data (e.g. `updatedAfter` in the future) returns **HTTP 404, `application/problem+json`**, not an empty CSV.
- FM key-rate series (`...KR.*.LEV`) contain a row for **every calendar day** (incl. weekends/holidays), not only
  change dates. `is_change_day` must therefore be derived by comparing with the previous day.
- Column sets differ by dataset (EST uses `CONF_STATUS`/`DATA_TYPE_EST`; FM uses `PROVIDER_FM_ID`); common:
  `KEY, TIME_PERIOD, OBS_VALUE, OBS_STATUS`. EST volume (`TT`) has `UNIT_MULT=6`, i.e. EUR millions.
- Coverage starts verified: EST WT 2019-10-01, FM DFR 1999-01-01, HICP latest 2026-10.

**Open issues**
- `make` is not installed on Windows by default; the runbook documents `scoop install make`.
- Metabase uses ~1.5 GB RAM; whole stack ~2.8 GB at idle (`docker stats`).
