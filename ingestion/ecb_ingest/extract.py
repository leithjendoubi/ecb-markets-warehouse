"""Extract one dataset from the ECB API and land the response unchanged in S3 (FR-01..FR-03).

Modes
- full:        no watermark yet -> startPeriod=config start (first run = full backfill, FR-02)
- incremental: watermark exists -> updatedAfter=watermark (only changed observations)
- backfill:    explicit start/end (manual DAG params) -> startPeriod/endPeriod; watermark untouched

The extractor never moves the watermark. It records the candidate (the request start time) in the
manifest; the loader advances the watermark after the rows are committed (docs/decisions/0002-...).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

from ecb_ingest.client import EcbClient
from ecb_ingest.config import DatasetConfig
from ecb_ingest.parsing import check_header, parse_csv
from ecb_ingest.s3 import S3Store
from ecb_ingest.state import WatermarkStore

log = logging.getLogger(__name__)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def api_timestamp(ts: datetime) -> str:
    """`updatedAfter` value: UTC, whole seconds. The ECB API answers HTTP 400 to fractional seconds
    (real response: tests/fixtures/exr_400_fractional_seconds.html). Truncating rounds the watermark
    down, so at worst an observation is fetched twice; staging keeps the latest version."""
    return ts.astimezone(UTC).replace(microsecond=0).isoformat()


class EmptyFullLoadError(RuntimeError):
    """A first full load returned no data: the series key is probably wrong."""


@dataclass(frozen=True)
class Manifest:
    dataset: str
    load_id: str
    mode: str
    source_url: str
    http_status: int
    s3_key: str | None
    rows_extracted: int
    request_started_at: str
    ingestion_date: str
    watermark_before: str | None
    watermark_candidate: str | None
    start_period: str | None
    end_period: str | None
    run_id: str | None = None
    detail: str = ""

    def to_json(self) -> bytes:
        return json.dumps(asdict(self), indent=2, sort_keys=True).encode("utf-8")

    @classmethod
    def from_json(cls, body: bytes) -> Manifest:
        return cls(**json.loads(body.decode("utf-8")))


def landing_key(dataset: str, ingestion_date: date, load_id: str) -> str:
    return f"raw/ecb/{dataset}/ingestion_date={ingestion_date.isoformat()}/{load_id}.csv"


def manifest_key(dataset: str, load_id: str) -> str:
    return f"_manifests/{dataset}/{load_id}.json"


def make_load_id(dataset: str, mode: str, now: datetime, start: str | None = None, end: str | None = None) -> str:
    if mode == "backfill":
        # Deterministic: re-running the same range replaces the same rows (delete+insert by load_id).
        return f"{dataset}-backfill-{start}-{end}"
    return f"{dataset}-{mode}-{now.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _validate_range(start: str | None, end: str | None) -> None:
    if (start is None) != (end is None):
        raise ValueError("backfill needs both start and end")
    if start is None or end is None:
        return
    if not (_DATE.match(start) and _DATE.match(end)):
        raise ValueError(f"start/end must be YYYY-MM-DD, got {start!r}/{end!r}")
    if start > end:
        raise ValueError(f"start {start} is after end {end}")


def run_extract(
    cfg: DatasetConfig,
    *,
    client: EcbClient,
    store: S3Store,
    watermarks: WatermarkStore,
    now: datetime | None = None,
    start: str | None = None,
    end: str | None = None,
    run_id: str | None = None,
) -> Manifest:
    _validate_range(start, end)
    now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    stored = watermarks.get(cfg.name)
    watermark = api_timestamp(datetime.fromisoformat(stored)) if stored else None

    if start is not None:
        mode, start_period, end_period, updated_after = "backfill", start, end, None
    elif watermark:
        mode, start_period, end_period, updated_after = "incremental", cfg.start_period, None, watermark
    else:
        mode, start_period, end_period, updated_after = "full", cfg.start_period, None, None

    load_id = make_load_id(cfg.name, mode, now, start, end)
    result = client.fetch(
        cfg.flow,
        cfg.key,
        fmt=cfg.format,
        start_period=start_period,
        end_period=end_period,
        updated_after=updated_after,
    )

    s3_key: str | None = None
    rows = 0
    if result.has_data:
        header, data_rows = parse_csv(result.body)
        if data_rows:
            check_header(cfg, header)
            rows = len(data_rows)
            s3_key = landing_key(cfg.name, now.date(), load_id)
            if store.exists(s3_key):
                # Only possible for a deterministic backfill load_id re-run on the same day.
                # Raw objects are write-once, so keep the first landing and load from it.
                existing = store.get_bytes(s3_key) or b""
                rows = len(parse_csv(existing)[1])
                log.warning("%s already landed at %s; reusing it (raw zone is immutable)", load_id, s3_key)
            else:
                store.put_immutable(s3_key, result.body, content_type="text/csv")

    if rows == 0:
        if mode == "full":
            raise EmptyFullLoadError(f"{cfg.name}: full load returned no data ({result.detail}); check the key")
        level = logging.WARNING if mode == "backfill" else logging.INFO
        log.log(level, "%s: no observations (%s mode): %s", cfg.name, mode, result.detail or "empty")

    manifest = Manifest(
        dataset=cfg.name,
        load_id=load_id,
        mode=mode,
        source_url=result.url,
        http_status=result.status_code,
        s3_key=s3_key,
        rows_extracted=rows,
        request_started_at=now.isoformat(),
        ingestion_date=now.date().isoformat(),
        watermark_before=watermark,
        watermark_candidate=None if mode == "backfill" else now.isoformat(),
        start_period=start_period,
        end_period=end_period,
        run_id=run_id,
        detail=result.detail,
    )
    store.put_bytes(manifest_key(cfg.name, load_id), manifest.to_json(), content_type="application/json")
    log.info("%s: %s rows, mode=%s, load_id=%s, s3_key=%s", cfg.name, rows, mode, load_id, s3_key)
    return manifest
