# 0002: Load ids, immutable landing and watermarks

**Context.** Spec §3/§4 and FR-02..04: incremental via `updatedAfter`, a per-dataset watermark in
`_state/watermarks.json` advanced only after a successful load, raw files never overwritten, loads idempotent
per `load_id`. A naive deterministic load id per day breaks with incremental extraction: the second run of a
day fetches nothing, and delete+insert of an empty file would wipe the first run's rows.

**Decision.**
- `full` (no watermark) and `incremental` loads get a unique id `{dataset}-{mode}-{UTC yyyymmddThhmmssZ}`;
  a re-run of the DAG creates a new id, finds no changes (HTTP 404) and lands nothing: a no-op.
- `backfill` loads (manual start/end) get a deterministic id `{dataset}-backfill-{start}-{end}`, so re-running a
  range replaces exactly the same raw rows. If the file already landed today it is reused, never overwritten.
- The extractor writes a manifest (`_manifests/{dataset}/{load_id}.json`) with the watermark candidate, which
  is the request start time in UTC, truncated to whole seconds (the API returns HTTP 400 for fractions).
- The loader advances the watermark after its transaction commits, only forward, never for backfills.
- Concurrency: one active DAG run (`max_active_runs=1`) and serialised load tasks make the read-modify-write
  of the single watermark JSON safe without S3 conditional writes.
- Raw tables are append-only per load; "latest version per (series_key, time_period)" is resolved in staging.

**Consequences.** Raw holds every revision the ECB published (useful for audit); marts stay duplicate-free.
Using the local clock for the watermark assumes clock skew is small compared with the 18:00 schedule; the
7-day dbt look-back and staging de-duplication make an occasional double fetch harmless.
