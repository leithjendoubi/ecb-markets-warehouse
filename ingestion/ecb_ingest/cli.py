"""Command-line entry point used by Airflow tasks and the Makefile.

    python -m ecb_ingest.cli ensure-bucket
    python -m ecb_ingest.cli extract --dataset exr [--start YYYY-MM-DD --end YYYY-MM-DD] [--run-id ID]

Logs go to stderr. The last stdout line is the machine-readable result (Airflow pushes it to XCom).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from ecb_ingest.client import EcbClient
from ecb_ingest.config import load_config
from ecb_ingest.extract import run_extract
from ecb_ingest.s3 import S3Store, make_client
from ecb_ingest.settings import EcbSettings, S3Settings
from ecb_ingest.state import WatermarkStore

log = logging.getLogger("ecb_ingest")


def _store() -> S3Store:
    settings = S3Settings.from_env()
    return S3Store(make_client(settings), settings.bucket)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def cmd_ensure_bucket(_: argparse.Namespace) -> int:
    store = _store()
    created = store.ensure_bucket()
    log.info("bucket %s %s", store.bucket, "created" if created else "already exists")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cfg = load_config()[args.dataset]
    store = _store()
    ecb = EcbSettings.from_env()
    with EcbClient(ecb.base_url, timeout_seconds=ecb.timeout_seconds) as client:
        manifest = run_extract(
            cfg,
            client=client,
            store=store,
            watermarks=WatermarkStore(store),
            start=args.start or None,
            end=args.end or None,
            run_id=args.run_id or None,
        )
    _emit({"dataset": manifest.dataset, "load_id": manifest.load_id, "rows_extracted": manifest.rows_extracted})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ecb-ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ensure-bucket", help="create the S3 bucket if missing").set_defaults(func=cmd_ensure_bucket)

    ex = sub.add_parser("extract", help="call the ECB API for one dataset and land the response in S3")
    ex.add_argument("--dataset", required=True, choices=sorted(load_config()))
    ex.add_argument("--start", help="backfill start (YYYY-MM-DD); needs --end")
    ex.add_argument("--end", help="backfill end (YYYY-MM-DD); needs --start")
    ex.add_argument("--run-id", help="orchestrator run id, recorded in the manifest")
    ex.set_defaults(func=cmd_extract)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
