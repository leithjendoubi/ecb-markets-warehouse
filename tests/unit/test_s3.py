import pytest

from ecb_ingest.s3 import ObjectExistsError, S3Store


def test_ensure_bucket_creates_once(fake_s3):
    s = S3Store(fake_s3, "lake")
    assert s.ensure_bucket() is True
    assert s.ensure_bucket() is False


def test_put_immutable_refuses_overwrite(store):
    store.put_immutable("raw/a.csv", b"x")
    with pytest.raises(ObjectExistsError):
        store.put_immutable("raw/a.csv", b"y")
    assert store.get_bytes("raw/a.csv") == b"x"


def test_get_missing_returns_none(store):
    assert store.get_bytes("nope") is None
    assert store.exists("nope") is False


def test_list_keys_by_prefix(store):
    store.put_bytes("raw/exr/1.csv", b"1")
    store.put_bytes("raw/est/1.csv", b"1")
    assert store.list_keys("raw/exr/") == ["raw/exr/1.csv"]
