# 0005: EXR freshness is measured from the publication time

**Context.** Spec §7: EXR source freshness warn after 24 h, error after 72 h. Using the observation date at
midnight as "loaded at" made the source look 37 h old at 14:45 CET even though the latest published rate
(previous day) was only ~23 h old. Using `ingested_at` instead would measure our pipeline, not the data.

**Decision.** `loaded_at_field` = observation date + 16:00 Europe/Berlin, the ECB's usual publication time for
euro reference rates (the series title states the 14:15 CET concertation). Freshness then means "hours since
the newest rate was published".

**Consequences.** During a normal week the check passes; after a weekend or a TARGET holiday it warns
(> 24 h) and errors only after 72 h without a new rate, e.g. a long Easter weekend or a broken pipeline.
Pipeline health (rows loaded per run) is tested separately on `ops.pipeline_runs`.
