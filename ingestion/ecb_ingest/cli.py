"""Command-line entry point used by Airflow tasks and the Makefile.

    python -m ecb_ingest.cli ensure-bucket
    python -m ecb_ingest.cli extract --dataset exr [--start YYYY-MM-DD --end YYYY-MM-DD] [--run-id ID]
    python -m ecb_ingest.cli load --dataset exr --load-id exr-full-20261124T170000Z [--run-id ID]
    python -m ecb_ingest.cli record-run --run-id ID --started-at 2026-11-24T17:00:00+00:00

Logs go to stderr. The last stdout line is the machine-readable result (Airflow pushes it to XCom).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

import psycopg

from ecb_ingest.client import EcbClient
from ecb_ingest.config import load_config
from ecb_ingest.extract import run_extract
from ecb_ingest.load import read_manifest, record_dag_run, run_load
from ecb_ingest.s3 import S3Store, make_client
from ecb_ingest.settings import EcbSettings, S3Settings, WarehouseSettings
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


def _connect() -> psycopg.Connection:
    return psycopg.connect(WarehouseSettings.from_env().conninfo(), autocommit=True)


def cmd_load(args: argparse.Namespace) -> int:
    cfg = load_config()[args.dataset]
    store = _store()
    manifest = read_manifest(store, args.dataset, args.load_id)
    with _connect() as conn:
        result = run_load(
            cfg, manifest, conn=conn, store=store, watermarks=WatermarkStore(store), dag_run_id=args.run_id or None
        )
    _emit(
        {
            "dataset": result.dataset,
            "load_id": result.load_id,
            "status": result.status,
            "rows_loaded": result.rows_loaded,
            "watermark_advanced": result.watermark_advanced,
        }
    )
    return 0


def cmd_record_run(args: argparse.Namespace) -> int:
    with _connect() as conn:
        loaded = record_dag_run(conn, dag_run_id=args.run_id, started_at=datetime.fromisoformat(args.started_at))
    _emit({"run_id": args.run_id, "rows_loaded": loaded})
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

    ld = sub.add_parser("load", help="load a landed file into raw.<dataset> (idempotent per load_id)")
    ld.add_argument("--dataset", required=True, choices=sorted(load_config()))
    ld.add_argument("--load-id", required=True)
    ld.add_argument("--run-id", help="orchestrator run id, recorded in ops.pipeline_runs")
    ld.set_defaults(func=cmd_load)

    rr = sub.add_parser("record-run", help="log a fully successful DAG run in ops.pipeline_runs")
    rr.add_argument("--run-id", required=True)
    rr.add_argument("--started-at", required=True, help="ISO-8601 with timezone")
    rr.set_defaults(func=cmd_record_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
