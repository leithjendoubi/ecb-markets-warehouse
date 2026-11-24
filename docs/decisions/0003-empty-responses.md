# 0003: "No data" is an HTTP 404, and its meaning depends on the mode

**Context.** The real API (fixture `tests/fixtures/exr_empty.csv`) answers HTTP 404 `application/problem+json`
"No Series was returned" when nothing matches. It gives the same answer for an unknown series key.

**Decision.** The client returns `has_data=False` for 404 and does not retry it. The extractor then decides:
- incremental: normal (nothing changed); no raw file, manifest with 0 rows, watermark still advances after load.
- backfill: warning (a range of holidays can be empty).
- full (first run): error `EmptyFullLoadError`, because a configured key must return history.
429/5xx/network errors are retried with exponential backoff (tenacity, 5 attempts); other 4xx fail fast.

**Consequences.** A typo in a key is caught on the first run instead of silently producing an empty warehouse.
