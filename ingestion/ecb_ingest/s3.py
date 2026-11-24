"""Thin S3 wrapper (boto3) for the raw landing zone on SeaweedFS.

Raw files are immutable: `put_immutable` refuses to overwrite an existing key.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ecb_ingest.settings import S3Settings


class ObjectExistsError(RuntimeError):
    """Raised when writing a raw object whose key already exists (raw zone is write-once)."""


def make_client(settings: S3Settings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
    )


def _is_not_found(err: ClientError) -> bool:
    code = str(err.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


class S3Store:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def ensure_bucket(self) -> bool:
        """Create the bucket if missing. Returns True if it was created."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return False
        except ClientError as err:
            if not _is_not_found(err):
                raise
        self.client.create_bucket(Bucket=self.bucket)
        return True

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as err:
            if _is_not_found(err):
                return False
            raise

    def get_bytes(self, key: str) -> bytes | None:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_not_found(err):
                return None
            raise
        return resp["Body"].read()

    def put_bytes(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def put_immutable(self, key: str, body: bytes, content_type: str = "text/csv") -> None:
        if self.exists(key):
            raise ObjectExistsError(f"s3://{self.bucket}/{key} already exists; raw objects are never overwritten")
        self.put_bytes(key, body, content_type)

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys
