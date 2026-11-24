"""CI: push the saved real ECB responses (tests/fixtures) through the real extract + load code into raw.*.

The API is replaced by an httpx MockTransport serving the fixture for each dataset and S3 by the in-memory
fake from tests/conftest.py, so CI never calls the live API. Each dataset is loaded as a first full load.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ecb_ingest.client import EcbClient  # noqa: E402
from ecb_ingest.config import load_config  # noqa: E402
from ecb_ingest.extract import run_extract  # noqa: E402
from ecb_ingest.load import run_load  # noqa: E402
from ecb_ingest.s3 import S3Store  # noqa: E402
from ecb_ingest.settings import WarehouseSettings  # noqa: E402
from ecb_ingest.state import WatermarkStore  # noqa: E402
from tests.conftest import FIXTURES, FakeS3Client  # noqa: E402

FIXTURE_FOR = {"exr": "exr_sample.csv", "est": "est_sample.csv", "fm": "fm_sample.csv", "hicp": "hicp_sample.csv"}


def main() -> int:
    store = S3Store(FakeS3Client(), "ci-lake")
    store.ensure_bucket()
    watermarks = WatermarkStore(store)
    with psycopg.connect(WarehouseSettings.from_env().conninfo(), autocommit=True) as conn:
        for name, cfg in load_config().items():
            body = (FIXTURES / FIXTURE_FOR[name]).read_bytes()
            transport = httpx.MockTransport(lambda request, body=body: httpx.Response(200, content=body))
            with EcbClient("https://fixtures.invalid/service", transport=transport, max_attempts=1) as client:
                manifest = run_extract(cfg, client=client, store=store, watermarks=watermarks, run_id="ci")
            result = run_load(cfg, manifest, conn=conn, store=store, watermarks=watermarks, dag_run_id="ci")
            print(f"{name}: {result.rows_loaded} rows loaded ({result.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
