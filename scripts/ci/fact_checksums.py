"""Print row counts + checksums of all fact tables (scripts/fact_checksums.sql) and the spec query
(scripts/checksum.sql). Used by CI to compare incremental vs full-refresh builds."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingestion"))

from ecb_ingest.settings import WarehouseSettings  # noqa: E402


def main() -> int:
    with psycopg.connect(WarehouseSettings.from_env().conninfo()) as conn:
        for script in ("checksum.sql", "fact_checksums.sql"):
            sql = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            for row in conn.execute(sql).fetchall():
                print(" | ".join(str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
