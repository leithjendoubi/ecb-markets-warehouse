"""M4 check: a change in seeds/currency_reference.csv creates a new SCD2 version in dim_currency.

Runs dbt (host install, same pins as the image) on a temp copy of the project, building into throwaway
schemas via DBT_SCHEMA_PREFIX, so the real warehouse history is untouched. Needs Postgres (make up / CI).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import psycopg
import pytest
from dbt.cli.main import dbtRunner

from ecb_ingest.settings import WarehouseSettings
from tests.conftest import ROOT

pytestmark = pytest.mark.integration

SCHEMAS = ("staging", "snapshots", "marts")


def _dbt(project: Path, *args: str) -> None:
    res = dbtRunner().invoke([*args, "--project-dir", str(project), "--profiles-dir", str(project), "--quiet"])
    assert res.success, f"dbt {' '.join(args)} failed: {res.exception}"


@pytest.fixture
def project(tmp_path, monkeypatch):
    dst = tmp_path / "ecb_warehouse"
    shutil.copytree(ROOT / "dbt/ecb_warehouse", dst, ignore=shutil.ignore_patterns("target", "logs"))
    prefix = f"it_{uuid.uuid4().hex[:6]}_"
    monkeypatch.setenv("DBT_SCHEMA_PREFIX", prefix)
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
    yield dst, prefix
    with psycopg.connect(WarehouseSettings.from_env().conninfo(), autocommit=True) as conn:
        for s in SCHEMAS:
            conn.execute(f"drop schema if exists {prefix}{s} cascade")


def _versions(prefix: str, code: str) -> list[tuple]:
    with psycopg.connect(WarehouseSettings.from_env().conninfo()) as conn:
        return conn.execute(
            f"select version_number, status, is_current, valid_to = timestamp '9999-12-31' "
            f"from {prefix}marts.dim_currency where currency_code = %s order by version_number",
            (code,),
        ).fetchall()


def test_seed_change_creates_new_scd2_version(project):
    path, prefix = project
    selector = ["--select", "currency_reference", "snap_currency", "dim_currency"]
    _dbt(path, "seed", "--select", "currency_reference")
    _dbt(path, "snapshot", "--select", "snap_currency")
    _dbt(path, "run", "--select", "dim_currency")
    assert _versions(prefix, "SEK") == [(1, "active", True, True)]

    seed = path / "seeds/currency_reference.csv"
    text = seed.read_text(encoding="utf-8")
    assert "SEK,Swedish krona,active,," in text
    seed.write_text(text.replace("SEK,Swedish krona,active,,", "SEK,Swedish krona,discontinued,2030-01-01,test"))

    _dbt(path, "seed", "--select", "currency_reference")
    _dbt(path, "snapshot", "--select", "snap_currency")
    _dbt(path, "run", "--select", "dim_currency")
    assert _versions(prefix, "SEK") == [(1, "active", False, False), (2, "discontinued", True, True)]
    assert _versions(prefix, "USD") == [(1, "active", True, True)]  # unchanged rows keep one version

    # spec §7 dim tests (one current per currency, no overlaps) still pass
    _dbt(path, "test", *selector)
