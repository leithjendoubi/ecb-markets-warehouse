"""Per-dataset watermarks stored in S3 at `_state/watermarks.json` (spec §4).

The watermark is the `updatedAfter` value for the next incremental request. It is advanced only after a
successful load (FR-02) and only forward. Concurrency: the DAG serialises load tasks and allows one active
run, so read-modify-write of the single JSON document is safe (docs/decisions/0002-load-ids-and-watermarks.md).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ecb_ingest.s3 import S3Store

WATERMARK_KEY = "_state/watermarks.json"


def _parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError(f"watermark must be timezone-aware, got {value!r}")
    return ts


class WatermarkStore:
    def __init__(self, store: S3Store, key: str = WATERMARK_KEY) -> None:
        self.store = store
        self.key = key

    def read_all(self) -> dict[str, dict[str, Any]]:
        body = self.store.get_bytes(self.key)
        if body is None:
            return {}
        return json.loads(body.decode("utf-8"))

    def get(self, dataset: str) -> str | None:
        entry = self.read_all().get(dataset)
        return entry["updated_after"] if entry else None

    def advance(self, dataset: str, updated_after: str, load_id: str, now: datetime | None = None) -> bool:
        """Move the dataset's watermark forward. Returns False (and changes nothing) when `updated_after`
        is not later than the stored value, so re-running an old load can never move it backwards."""
        new_ts = _parse_ts(updated_after)
        state = self.read_all()
        current = state.get(dataset)
        if current and _parse_ts(current["updated_after"]) >= new_ts:
            return False
        state[dataset] = {
            "updated_after": new_ts.isoformat(),
            "load_id": load_id,
            "advanced_at": (now or datetime.now(UTC)).isoformat(),
        }
        body = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
        self.store.put_bytes(self.key, body, content_type="application/json")
        return True
