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
- Memory use of the stack: measure with `make stats` (no figure recorded here: only measured numbers are published).

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

## M5: Facts, marts, singular tests, docs (2026-11-24)
**Built**
- Facts (incremental delete+insert, ADR 0008): `fct_fx_rate_daily` (rate, previous rate, daily return %,
  30-day vol), `fct_policy_rate_daily` (calendar spine, bounded forward fill, is_change_day; ADR 0007),
  `fct_estr_daily`, `fct_inflation_monthly`. Intermediate pivots `int_policy_rates_pivoted`, `int_estr_pivoted`.
- Marts: `mart_rates_monthly` (avg EUR STR, month-end DFR/MRO/MLF, HICP YoY, real EUR STR and real DFR),
  `mart_fx_performance` (MTD/YTD change, month-end 30-day vol), `mart_pipeline_health` (Q4; Metabase reads marts only).
- Tests: FK relationships, grain uniqueness, rate > 0, |daily return| < 10 (warn), no missing working days
  (warn), policy spine contiguous, rows loaded > 0 on working days (error), docs for every model/column.
- `scripts/fact_checksums.sql`, `scripts/check_dbt_docs.py` (+ unit test), `make docs-check`.

**Checks**
- `make dbt-build`: PASS=114 WARN=1 ERROR=0. The warning is real data: CHF 2015-01-15, -14.40% (SNB removed
  the EUR/CHF floor); severity warn per spec §7.
- Full refresh = incremental: identical row counts and checksums for all 4 facts after (a) a normal incremental
  run, (b) deleting the last 20 days and running incrementally, (c) `--full-refresh`.
  Spec checksum: n = 30,450, md5 f025dcf3c13a34e30c3201007da042f8.
- Lineage/docs: `make docs-check` -> "checked 23 nodes: OK" (every node and DB column documented, every model has parents).
- `make lint` clean; pytest 56 passed (unit + integration).

**Found**
- MRR_FR has no data 2000-06-28..2008-10-14 (variable-rate tenders); bounded forward fill keeps MRO NULL there
  (ADR 0007). The ECB minimum bid rate series covers that gap and is listed as an optional extension.

**Open issues**
- ECB revisions older than the 7-day look-back need `dbt build --full-refresh` (documented in ADR 0008).

## M6: Metabase dashboard, CI workflow, pre-commit (2026-11-24)
**Built**
- `docs/dashboard.md`: 9 native-SQL cards for Q1-Q4, marts only; single source for
  `scripts/metabase_setup.py` (`make dashboard`: idempotent API setup, read-only connection, runs every card).
- `scripts/dashboard_screenshot.py` (`make dashboard-screenshot`) -> `docs/img/dashboard.png`.
- `.github/workflows/ci.yml` (jobs lint-unit, integration-dbt, dag) driven by `scripts/ci/start_postgres.sh`,
  `scripts/ci/integration.sh`, `scripts/ci/load_fixtures.py`, `scripts/ci/fact_checksums.py`.
- `.pre-commit-config.yaml` (pre-commit-hooks v6.0.0, ruff v0.17.6, sqlfluff 4.5.0, no-.env guard); hook installed.

**Checks**
- `make dashboard`: 9 cards created, each query executed OK as the read-only user; that user gets
  "permission denied for schema raw". Screenshot reviewed: all Q1-Q4 cards render with data.
- CI simulated locally in clean Linux containers from the git-tracked files only:
  lint-unit: ruff + sqlfluff clean, 52 unit tests passed; integration-dbt: 5 integration tests passed, fixtures
  loaded (exr 110 / est 22 / fm 45 / hicp 34 rows), `dbt build` PASS=115 ERROR=0, docs check OK,
  full-refresh checksums identical; dag: 5 DAG tests passed on the standalone image.
- Broken test fails CI: removing USD from the accepted currencies -> `FAIL 1 accepted_values_stg_ecb__exr...`,
  `ERROR=1 SKIP=56`, `integration.sh` exit code 1.
- `pre-commit run --all-files`: all hooks passed.

**Found and fixed**
- Metabase displays at most 2,000 rows per question: the daily Q2.1 series hit the cap, now weekly (374 rows).
- The S3 smoke test needs SeaweedFS: marked `stack`, excluded from CI (`integration and not stack`).

**Open issues**
- CI has not run on GitHub yet: the repository has no remote. Push (see README) and check the Actions tab;
  the local replica above runs the same scripts.

## M7: README, ADRs, fresh-clone check (2026-11-24)
**Built**
- `README.md` per spec §12: pitch + business questions, architecture diagram (mermaid), 3-command quick start,
  data model (ER diagram + grains), dashboard screenshot, ADR index, data quality, idempotency proof, run time,
  production changes, limitations, CI badge.
- `make demo` (first run + dashboard) and a blocking `scripts/run_dag.sh` behind `make trigger` / `make backfill`;
  `make dashboard` now runs inside the Airflow container (no host Python needed); `make stats`.
- Removed performance numbers that did not come from `ops.pipeline_runs` or `scripts/` (memory figures, a
  start-up time estimate) (only measured numbers are published).

**Checks**
- Run time (`make benchmark`, `ops.pipeline_runs`): median 27.9 s, min 26.0 s, max 35.0 s over the 5 most recent
  incremental DAG runs (2026-11-24 14:11-14:14 UTC, manually triggered, no new data).
- Fresh clone (`git clone` into a new folder, new compose project = empty volumes), following only the README:
  `cp .env.example .env` → `make up` (all services healthy) → `make demo` (DAG run success; 9 dashboard cards
  created and executed). Loaded exr 30,450 / est 3,662 / fm 27,539 / hicp 142 rows; spec checksum
  n = 30,450, md5 f025dcf3c13a34e30c3201007da042f8 — identical to the original stack. Clone and volumes removed.
- `make lint` clean; `make test` 52 passed; `make dag-test` 5 passed.

**Open issues / left for the owner**
- Push to GitHub and confirm the CI badge turns green (simulated locally in M6, never run on GitHub).
- Optional: ECB minimum bid rate series for the 2000-2008 MRO gap (ADR 0007).
- Run-time figure is from same-day manual runs; re-run `make benchmark` after 5 scheduled 18:00 runs.
