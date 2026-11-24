# 0008: Incremental facts: delete+insert with look-back and a window buffer

**Context.** Spec §3/§5: incremental facts with a 7-day look-back for ECB revisions; spec §7 requires full
refresh and incremental runs to produce the same checksum. Window functions (previous rate, 30-day
volatility, forward fill, month-on-month change) give different answers if an incremental run only reads the
last 7 days.

**Decision.**
- Strategy `delete+insert` on the fact grain (`currency_code, full_date`; `full_date`; `month_start`).
- An incremental run rewrites rows from `max(full_date) - lookback_days` (7), but reads
  `window_buffer_days` (90) extra history so window functions see the same rows as a full refresh.
- HICP is monthly and gets revised for longer: look-back of 12 months.
- Marts are plain tables rebuilt each run (small).

**Consequences.** Proven on the real data: checksums of all four facts are identical after a normal incremental
run, after deleting the last 20 days and running incrementally, and after `--full-refresh`
(`scripts/fact_checksums.sql`, `scripts/checksum.sql`). A revision older than the look-back is not picked up
incrementally; `dbt build --full-refresh` repairs it (runbook).
