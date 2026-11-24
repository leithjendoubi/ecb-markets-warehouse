"""Command-line entry point used by Airflow tasks and the Makefile.

python -m ecb_ingest.cli ensure-bucket
"""

from __future__ import annotations

import argparse
import logging
import sys

from ecb_ingest.s3 import S3Store, make_client
from ecb_ingest.settings import S3Settings

log = logging.getLogger("ecb_ingest")


def _store() -> S3Store:
    settings = S3Settings.from_env()
    return S3Store(make_client(settings), settings.bucket)


def cmd_ensure_bucket(_: argparse.Namespace) -> int:
    store = _store()
    created = store.ensure_bucket()
    log.info("bucket %s %s", store.bucket, "created" if created else "already exists")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ecb-ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ensure-bucket", help="create the S3 bucket if missing").set_defaults(func=cmd_ensure_bucket)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
