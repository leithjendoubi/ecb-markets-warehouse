"""Shared pytest fixtures. Unit tests are offline: a dict-backed fake replaces S3, fixtures replace the API."""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from ecb_ingest.s3 import S3Store

# The DAG tests need Airflow, which only exists in the Airflow container (make dag-test). Check a real
# Airflow module: the repo's own airflow/ folder is importable as a namespace package.
try:
    _has_airflow = importlib.util.find_spec("airflow.dag_processing") is not None
except ModuleNotFoundError:
    _has_airflow = False
collect_ignore: list[str] = [] if _has_airflow else ["dags"]

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_dotenv() -> None:
    """Integration tests run on the host against the compose stack; read .env without extra deps."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _client_error(code: str, op: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


class FakeS3Client:
    """The subset of the boto3 S3 client used by ecb_ingest.s3.S3Store."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.put_calls = 0

    def head_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803 (boto3 casing)
        if Bucket not in self.buckets:
            raise _client_error("404", "HeadBucket")
        return {}

    def create_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803
        self.buckets.setdefault(Bucket, {})
        return {}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        if Key not in self.buckets.get(Bucket, {}):
            raise _client_error("404", "HeadObject")
        return {"ContentLength": len(self.buckets[Bucket][Key])}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        if Key not in self.buckets.get(Bucket, {}):
            raise _client_error("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(self.buckets[Bucket][Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = "") -> dict[str, Any]:  # noqa: N803
        if Bucket not in self.buckets:
            raise _client_error("NoSuchBucket", "PutObject")
        self.buckets[Bucket][Key] = bytes(Body)
        self.put_calls += 1
        return {}

    def get_paginator(self, name: str) -> Any:
        assert name == "list_objects_v2"
        client = self

        class _Paginator:
            def paginate(self, Bucket: str, Prefix: str = ""):  # noqa: N803
                keys = sorted(k for k in client.buckets.get(Bucket, {}) if k.startswith(Prefix))
                yield {"Contents": [{"Key": k} for k in keys]} if keys else {}

        return _Paginator()


@pytest.fixture
def fake_s3() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture
def store(fake_s3: FakeS3Client):
    s = S3Store(fake_s3, "test-bucket")
    s.ensure_bucket()
    return s


@pytest.fixture
def fixture_bytes():
    def _read(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return _read
