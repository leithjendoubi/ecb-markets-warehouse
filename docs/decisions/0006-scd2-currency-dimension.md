# 0006: SCD2 currency dimension from a seed snapshot

**Context.** FR-07: `dim_currency` as SCD Type 2 via a dbt snapshot (check strategy) on
`seeds/currency_reference.csv`. Snapshot validity starts when the snapshot first ran (2026), but FX facts start
in 2015, so a plain `rate_date between dbt_valid_from and dbt_valid_to` join would leave history unmatched.

**Decision.**
- Snapshot defined in YAML (`snapshots/snap_currency.yml`, dbt >= 1.9), `check_cols` = name, status,
  last_rate_date, notes; `hard_deletes: invalidate`; current rows get `valid_to = 9999-12-31`.
- In `dim_currency` the first version of each currency is back-dated to 1999-01-01; later versions start at
  the snapshot time of the change. `valid_from` inclusive, `valid_to` exclusive; `currency_sk = dbt_scd_id`.
- Seed names come from the ECB series titles; HRK (Croatian kuna, last rate 2022-12-30 per fixture
  `exr_hrk.csv`) is included as `discontinued` to model a currency leaving the euro-area FX set.
- The SCD2 behaviour is proven by `tests/integration/test_scd2_currency.py`, which edits a temp copy of the
  seed and builds into throwaway schemas (`DBT_SCHEMA_PREFIX`), keeping the real history clean.

**Consequences.** Facts resolve to the version valid on the rate date. Changing a row in the seed and running
the DAG creates a new version; the version history is only as granular as the snapshot runs.
