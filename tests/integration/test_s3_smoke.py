"""M1 check: boto3 can upload to / read from SeaweedFS on :8333. Needs `make up`."""

import uuid

import pytest

from ecb_ingest.s3 import S3Store, make_client
from ecb_ingest.settings import S3Settings

pytestmark = pytest.mark.integration


def test_boto3_roundtrip_against_seaweedfs():
    settings = S3Settings.from_env()
    store = S3Store(make_client(settings), settings.bucket)
    store.ensure_bucket()
    key = f"_smoke/{uuid.uuid4()}.txt"
    store.put_immutable(key, b"hello seaweedfs", content_type="text/plain")
    assert store.get_bytes(key) == b"hello seaweedfs"
    assert key in store.list_keys("_smoke/")
    store.client.delete_object(Bucket=settings.bucket, Key=key)
