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

## M2: Extractor (2026-11-24)
**Built**
- `ingestion/ecb_ingest/config.yaml` + `config.py`: 4 datasets (flow, key, start period, raw table, CSV->raw
  column map). A unit test asserts every mapped column exists in the saved real responses.
- `client.py`: httpx client; key kept verbatim in the path (`+`), query values percent-encoded; tenacity retries
  (5 attempts, exponential backoff) on network errors, 408/425/429/5xx; 404 => `has_data=False`.
- `state.py`: watermarks in `s3://$S3_BUCKET/_state/watermarks.json`, forward-only `advance()`.
- `extract.py`: modes full / incremental / backfill; lands the response bytes unchanged at
  `raw/ecb/{dataset}/ingestion_date=YYYY-MM-DD/{load_id}.csv` (write-once), writes a manifest.
- `cli.py extract`: JSON result on the last stdout line for XCom.
- ADRs 0001 (pipeline venv), 0002 (load ids + watermarks), 0003 (404 semantics).

**Checks**
- `make test`: 42 passed, offline (httpx MockTransport serving fixtures; dict-backed fake S3).
- `ruff check` + `ruff format --check`: clean.
- Live check (throwaway bucket, deleted afterwards): full EXR extract landed 30,450 rows; with the watermark
  set, the next run sent `updatedAfter`, got 404, landed nothing (raw object count stayed 1): no-op.

**Found and fixed**
- The API rejects `updatedAfter` with fractional seconds (HTTP 400, saved as
  `tests/fixtures/exr_400_fractional_seconds.html`). Watermarks are now truncated to whole seconds (+ tests).

**Open issues**
- The watermark is advanced by the loader (M3); until then nothing moves it in production.

## M3: Loader, ops.pipeline_runs, Airflow DAG (2026-11-24)
**Built**
- DDL: `raw.exr/est/fm/hicp` (configured API columns as text + load_id, row_num, extracted_at, ingested_at,
  source_url, s3_key; PK (load_id, row_num)), `ops.pipeline_runs` (FR-09 columns + mode, dag_run_id, error).
  A unit test keeps `02_raw.sql` in sync with `config.yaml`.
- `load.py`: one transaction = delete by load_id + COPY + pipeline_runs row; row-count cross-checks
  (file vs manifest, copied vs stored); failures roll back and are logged as `failed`; watermark advanced after commit.
- `airflow/dags/ecb_daily.py`: Mon-Fri 18:00 Europe/Berlin, catchup=False, max_active_runs=1, retries x3 with
  exponential backoff, `extract` and `load` dynamically mapped over 4 datasets (loads serialised), then
  `dbt build` -> `dbt source freshness` -> `record_run` (writes the 'all' row used for run-time stats).
  Params `start`/`end` = backfill (`make backfill START=.. END=..`).
- dbt skeleton (project, env-var profile, sources with EXR freshness warn 24 h / error 72 h).
- `scripts/raw_counts.sql`, `scripts/checksum.sql`, `scripts/benchmark.sql`.

**Checks**
- First DAG run (full history) succeeded: exr 30,450 / est 3,662 / fm 27,539 / hicp 142 rows (ops.pipeline_runs).
- DAG run again the same day (twice: the unpause-scheduled run and a manual run): every load `no_data`;
  `scripts/raw_counts.sql` before/after: identical counts and checksums.
- 2-year backfill 2024-11-25..2026-11-24 run twice: exr 5,090 / est 1,018 / fm 2,190 / hicp 23 rows each time;
  raw counts + checksums identical after the re-run; watermarks unchanged by the backfill.
- `make test` + integration: 50 passed (incl. load-twice idempotency, failure rollback, no_data path).
- `make dag-test`: no import errors, 5 DAG structure tests passed (inside the Airflow container).

**Open issues**
- Unpausing a `catchup=False` DAG immediately schedules the latest cron slot once (Airflow behaviour); harmless here.

## M4: dbt sources, staging, dim_date, seed + snapshot, dim_currency (2026-11-24)
**Built**
- Sources `raw.exr/est/fm/hicp`, `ops.pipeline_runs`; EXR freshness warn 24 h / error 72 h, measured from
  16:00 Europe/Berlin on the observation date (ADR 0005).
- Staging views `stg_ecb__exr/est/fm/hicp` (typed, latest version per (series_key, time_period) via macro
  `latest_observation`), `stg_ops__pipeline_runs`.
- `dim_date` (1999-2030, weekend / TARGET holiday / TARGET business day / ECB working day flags; ADR 0004).
- Seed `currency_reference` (names from ECB titles, HRK discontinued), YAML snapshot `snap_currency` (check),
  SCD2 `dim_currency` (ADR 0006). Generic tests `unique_combination`, `expression_is_true`; singular tests for
  one current row per currency, non-overlapping versions, EXR only on TARGET business days.
- `.sqlfluff` (jinja templater + dbt builtins, lowercase policy), `DBT_SCHEMA_PREFIX` for throwaway builds.

**Checks**
- `make dbt-build`: PASS=59 WARN=0 ERROR=0.
- `make freshness`: raw.exr PASS.
- Calendar cross-check 2015-01-02..2026-11-23: 3,045 TARGET business days = 3,045 ECB working days, 0 mismatches.
- SCD2: `tests/integration/test_scd2_currency.py` changes SEK in a temp seed copy -> v1 closed, v2 current;
  USD still one version; dim tests pass. Throwaway schemas dropped afterwards.
- `make lint` (ruff + sqlfluff) clean; pytest 51 passed (unit + integration).

**Open issues**
- dbt prints "dbt v2 is available"; staying on dbt-core 1.12 as pinned in pyproject.toml.
