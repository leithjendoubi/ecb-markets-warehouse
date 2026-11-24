# ECB Markets Warehouse: Project Specification (v1.1)

Author: Leith Jendoubi · Data Engineering Portfolio, Project 01 of 03
Repository: `ecb-markets-warehouse`

## §1 Summary
Treasury and FX-risk teams need one trusted daily view of euro exchange rates, ECB policy rates and euro-area
inflation. This project pulls official ECB statistics **incrementally**, lands them unchanged in S3-compatible
storage, loads them into PostgreSQL, and models them with **dbt** into a tested Kimball star schema, orchestrated
daily by **Apache Airflow 3**, served in **Metabase**.

Skills shown: ELT, incremental and idempotent loads, backfills, Kimball star schema, SCD Type 2, dbt tests,
source freshness, orchestration, CI.

## §2 Business questions and success criteria
| # | Question | Answered by |
|---|---|---|
| Q1 | How have major currencies moved vs the euro (daily, MTD, YTD), and how volatile are they? | fct_fx_rate_daily, mart_fx_performance |
| Q2 | How do ECB policy-rate decisions line up with €STR and FX moves? | fct_policy_rate_daily, fct_estr_daily |
| Q3 | What is euro-area inflation doing; what is the real (inflation-adjusted) €STR? | mart_rates_monthly |
| Q4 | Is today's data complete and fresh? | dbt source freshness, gap tests, ops.pipeline_runs |

Success criteria:
- Coverage: FX from 2015-01-01 (10 currencies), €STR from 2019-10-01, policy rates from 1999, HICP from 2015.
- Idempotency: re-running any day/backfill changes nothing (row count + checksum identical).
- Incremental: daily run fetches only changed observations (`updatedAfter`).
- Every model tested; zero failing `error` tests on main.
- Run time: measured median of 5 daily runs from ops.pipeline_runs (no invented numbers).
- Fresh clone to working dashboard following only the README.

Out of scope: cloud deployment, streaming, forecasting, non-ECB sources.

## §3 Data sources (ECB Data Portal, free, no API key)
Pattern: `https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod=...&updatedAfter=...`
`+` joins several values in one key position.

| Dataset | Series key | Frequency | Use |
|---|---|---|---|
| EXR exchange rates | `D.USD+GBP+CHF+JPY+CNY+SEK+NOK+PLN+CAD+AUD.EUR.SP00.A` | ECB working days | FX fact |
| EST €STR | `B.EU000A2X2A25.WT` (rate), `B.EU000A2X2A25.TT` (volume) | TARGET days | money-market rate |
| FM key ECB rates | `D.U2.EUR.4F.KR.DFR.LEV`, `D.U2.EUR.4F.KR.MRR_FR.LEV`, `D.U2.EUR.4F.KR.MLFR.LEV` | date of change | policy rates |
| HICP inflation | `M.U2.N.000000.4D0.ANR` | monthly | inflation |

Facts that shape the design:
- The ECB revises data: keep the latest version per (series_key, time_period); incremental facts use a 7-day look-back.
- `updatedAfter` returns only observations changed since a timestamp: store one watermark per dataset, advance it only after a successful load.
- The old `ICP` dataset was replaced by `HICP`. Verify all keys on Day 1.
- FX follows ECB working days; policy rates exist only on change dates → align on one daily date spine.
- Currencies can disappear (Croatia adopted the euro in 2023) → SCD2 currency dimension.
- **Day-1 rule:** save one real response per dataset in `tests/fixtures/` before writing any parser.

## §4 Architecture
```
Airflow 3 DAG ecb_daily (Mon-Fri 18:00 Europe/Berlin, retries x3, backfill params)
ECB API -> Python extractor -> SeaweedFS S3: raw/ecb/{dataset}/ingestion_date=YYYY-MM-DD/{load_id}.csv
        -> loader (COPY, one transaction, delete+insert by load_id) -> Postgres raw.*
        -> dbt: staging (views) -> marts (tables, incremental) + snapshots + tests -> Metabase
ops.pipeline_runs logs every load. CI: GitHub Actions (ruff, pytest on fixtures, dbt build on Postgres service).
```
| Component | Responsibility | Key choice |
|---|---|---|
| Extractor | call API per dataset, write raw file, update watermark | retries + backoff; watermark only after success |
| SeaweedFS (S3 API) | immutable raw landing + `_state/watermarks.json` | never overwrite; boto3 client |
| Loader | COPY into raw.* with load_id, ingested_at, source_url | delete-then-insert by load_id, one transaction |
| dbt Core | staging → marts, snapshots, tests, docs | incremental facts, 7-day look-back |
| Airflow 3 | schedule, retry, backfill | dynamic task mapping per dataset |
| Metabase | dashboards | reads marts only, read-only DB user |

Daily sequence: extract[dataset] (mapped ×4) → load[dataset] (mapped ×4) → dbt build → dbt source freshness.

## §5 Data model (Kimball star schema)
| Table | Grain | Load | Notes |
|---|---|---|---|
| dim_date | calendar day 1999–2030 | full rebuild | is_weekend, is_ecb_working_day (from EXR dates) |
| dim_currency | currency × version | dbt snapshot (check) on seed currency_reference.csv | currency_sk, valid_from, valid_to, is_current, status |
| fct_fx_rate_daily | currency × ECB working day | incremental delete+insert, 7-day look-back | rate_per_eur numeric(18,6), daily_return_pct, vol_30d_pct |
| fct_policy_rate_daily | calendar day | incremental | DFR, MRO, MLF forward-filled onto date spine; is_change_day |
| fct_estr_daily | TARGET day | incremental | estr_pct, total_volume_eur_mn |
| fct_inflation_monthly | month | incremental | hicp_yoy_pct |
| mart_rates_monthly | month | table | avg €STR, DFR at month end, HICP YoY, real_estr = €STR − HICP |
| mart_fx_performance | currency × month | table | MTD/YTD change, 30-day vol |

## §6 Requirements
- FR-01 Extract each dataset as CSV, config-driven (flow, key, start date in config.yaml).
- FR-02 Incremental via `updatedAfter` + per-dataset watermark; first run = full backfill.
- FR-03 Land raw responses unchanged and immutably in S3, partitioned by dataset and ingestion date.
- FR-04 Load into raw.* with load_id, ingested_at, source_url; idempotent per load_id.
- FR-05 Staging: type, rename, keep latest value per (series_key, time_period).
- FR-06 Build §5 tables at declared grains.
- FR-07 dim_currency as SCD2 via snapshot.
- FR-08 Airflow DAG as in §4; retries ×3 with exponential backoff; catchup=False; manual backfill params start/end.
- FR-09 ops.pipeline_runs: dataset, load_id, rows_extracted, rows_loaded, started_at, finished_at, status.
- FR-10 Metabase dashboard for Q1–Q4; SQL saved in docs/dashboard.md.
- NFR: idempotent, reproducible (pinned versions, `make up`), observable (run log), no secrets in Git,
  ruff + sqlfluff clean, runs on a 16 GB laptop.

## §7 Data quality and tests
| Layer | Check | Severity |
|---|---|---|
| Source | EXR freshness: warn 24 h, error 72 h | warn/error |
| Staging | (series_key, time_period) unique + not null | error |
| Staging | rate_per_eur > 0; currency in accepted list | error |
| Dim | exactly one is_current row per currency | error |
| Fact | foreign keys resolve | error |
| Fact | no missing ECB working days for active currencies | warn |
| Fact | abs(daily_return_pct) < 10 | warn |
| Pipeline | rows loaded > 0 on working days | error |

Tests: pytest unit tests on fixtures (URL building, parsing, watermark, empty responses); integration test
(load fixture twice → same counts); dbt tests on every model; full-refresh vs incremental checksum.

Idempotency proof query (keep in scripts/checksum.sql):
```sql
select count(*) as n,
       md5(string_agg(currency_code || full_date || rate_per_eur, ',' order by currency_code, full_date)) as checksum
from marts.fct_fx_rate_daily f join marts.dim_currency c using (currency_sk);
```

## §8 Repository layout
```
ecb-markets-warehouse/
├── README.md  Makefile  docker-compose.yml  .env.example  pyproject.toml  .pre-commit-config.yaml
├── infra/s3.json                  # local-only S3 credentials for SeaweedFS
├── ingestion/ecb_ingest/  client.py extract.py load.py state.py config.yaml
├── airflow/dags/ecb_daily.py
├── dbt/ecb_warehouse/  models/{staging,intermediate,marts}  snapshots/  seeds/  tests/
├── sql/init/                      # schemas raw, ops
├── scripts/                       # checksum.sql, benchmark helpers
├── tests/{unit,integration,fixtures}/
├── docs/  spec.md  PROGRESS.md  dashboard.md  runbook.md  decisions/  img/
└── .github/workflows/ci.yml
```

## §9 Milestones (each ends with checks + one commit)
| M | Build | Done when |
|---|---|---|
| M1 | Compose stack (Postgres 16, SeaweedFS S3, Airflow 3 LocalExecutor, Metabase), Makefile, .env.example, runbook; save ECB fixtures | `make up` healthy; Airflow :8080, Metabase :3000 load; boto3 test upload to :8333 works; fixtures committed |
| M2 | Extractor: client, config, watermark state, landing to S3; unit tests | offline tests green; second run with no new data = no-op |
| M3 | Loader + ops.pipeline_runs; Airflow DAG (mapping, retries, params) | DAG twice for one day → identical counts; 2-year backfill done |
| M4 | dbt: sources + freshness, staging, dim_date, seed + snapshot, dim_currency | `dbt build` green; seed change creates SCD2 version |
| M5 | Facts, marts, singular tests, schema.yml docs | full refresh = incremental checksum; lineage complete |
| M6 | Metabase dashboard SQL, CI workflow, pre-commit | CI green; broken test fails CI; screenshot in docs/img/ |
| M7 | README (pitch, diagram, quick start, model, decisions, quality, backfill, production changes, limits), ADRs | fresh clone runs from README; every number sourced |

Stretch (only after M7): Data Vault version of FX model, Great Expectations/Soda, failure alerts, cross-rates.

## §12 README outline
Pitch + business question · architecture diagram · quick start (3 commands) · data model · dashboard screenshot ·
design decisions (link ADRs) · data quality · idempotency proof · what I'd change in production · limitations ·
CI badge.
