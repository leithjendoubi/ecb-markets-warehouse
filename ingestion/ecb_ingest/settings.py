"""Runtime configuration from environment variables (see .env.example). No defaults for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _req(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"environment variable {name} is required (see .env.example)")
    return value


@dataclass(frozen=True)
class S3Settings:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str

    @classmethod
    def from_env(cls) -> S3Settings:
        return cls(
            endpoint_url=_req("S3_ENDPOINT_URL"),
            access_key=_req("S3_ACCESS_KEY"),
            secret_key=_req("S3_SECRET_KEY"),
            bucket=_req("S3_BUCKET"),
            region=os.environ.get("S3_REGION", "us-east-1"),
        )


@dataclass(frozen=True)
class WarehouseSettings:
    host: str
    port: int
    dbname: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> WarehouseSettings:
        return cls(
            host=_req("WAREHOUSE_HOST"),
            port=int(os.environ.get("WAREHOUSE_PORT", "5432")),
            dbname=_req("WAREHOUSE_DB"),
            user=_req("WAREHOUSE_USER"),
            password=_req("WAREHOUSE_PASSWORD"),
        )

    def conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} application_name=ecb_ingest"
        )


@dataclass(frozen=True)
class EcbSettings:
    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> EcbSettings:
        return cls(
            base_url=os.environ.get("ECB_BASE_URL", "https://data-api.ecb.europa.eu/service").rstrip("/"),
            timeout_seconds=float(os.environ.get("ECB_TIMEOUT_SECONDS", "120")),
        )
