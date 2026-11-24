"""Integration (spec §7): load the same fixture twice -> identical counts and checksum.

Runs against the warehouse Postgres (make up, or the CI service) in a throwaway schema; S3 and the API are
replaced by the offline fakes, so no live API call is made.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

import httpx
import psycopg
import pytest

from ecb_ingest.client import EcbClient
from ecb_ingest.config import load_config
from ecb_ingest.extract import run_extract
from ecb_ingest.load import LoadError, record_dag_run, run_load
from ecb_ingest.settings import WarehouseSettings
from ecb_ingest.state import WatermarkStore

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 24, 17, 5, 0, tzinfo=UTC)


@pytest.fixture
def conn():
    with psycopg.connect(WarehouseSettings.from_env().conninfo(), autocommit=True) as c:
        yield c


@pytest.fixture
def schema(conn):
    name = f"it_{uuid.uuid4().hex[:8]}"
    conn.execute(f"create schema {name}")
    conn.execute(f"create table {name}.exr (like raw.exr including all)")
    conn.execute(f"create table {name}.pipeline_runs (like ops.pipeline_runs including all)")
    yield name
    conn.execute(f"drop schema {name} cascade")


def api_client(fixture_bytes, name="exr_sample.csv"):
    def handler(request):
        return httpx.Response(200, content=fixture_bytes(name))

    return EcbClient("https://example.test/service", transport=httpx.MockTransport(handler), max_attempts=1)


def snapshot(conn, table):
    return conn.execute(
        f"select count(*), md5(string_agg(series_key || time_period || obs_value, ',' "
        f"order by series_key, time_period)) from {table}"
    ).fetchone()


def test_loading_the_same_load_id_twice_is_idempotent(conn, schema, store, fixture_bytes):
    cfg = dataclasses.replace(load_config()["exr"], raw_table=f"{schema}.exr")
    runs = f"{schema}.pipeline_runs"
    wm = WatermarkStore(store)
    m = run_extract(cfg, client=api_client(fixture_bytes), store=store, watermarks=wm, now=NOW)

    r1 = run_load(cfg, m, conn=conn, store=store, watermarks=wm, dag_run_id="it-1", runs_table=runs)
    first = snapshot(conn, cfg.raw_table)
    r2 = run_load(cfg, m, conn=conn, store=store, watermarks=wm, dag_run_id="it-2", runs_table=runs)
    second = snapshot(conn, cfg.raw_table)

    assert first == second and first[0] == 110
    assert (r1.rows_loaded, r2.rows_loaded) == (110, 110)
    assert r1.watermark_advanced is True and r2.watermark_advanced is False  # forward-only
    assert wm.get("exr") == NOW.isoformat()
    statuses = conn.execute(f"select status, rows_loaded from {runs} order by run_pk").fetchall()
    assert statuses == [("success", 110), ("success", 110)]


def test_no_data_load_logs_no_data_and_advances_watermark(conn, schema, store):
    cfg = dataclasses.replace(load_config()["exr"], raw_table=f"{schema}.exr")
    runs = f"{schema}.pipeline_runs"
    wm = WatermarkStore(store)
    wm.advance("exr", "2026-11-23T17:00:00+00:00", "old")

    def handler(request):
        return httpx.Response(404, json={"detail": "No Series was returned"})

    client = EcbClient("https://example.test/service", transport=httpx.MockTransport(handler), max_attempts=1)
    m = run_extract(cfg, client=client, store=store, watermarks=wm, now=NOW)
    r = run_load(cfg, m, conn=conn, store=store, watermarks=wm, runs_table=runs)
    assert (r.status, r.rows_loaded) == ("no_data", 0)
    assert wm.get("exr") == NOW.isoformat()
    assert snapshot(conn, cfg.raw_table)[0] == 0


def test_failed_load_rolls_back_and_is_logged(conn, schema, store, fixture_bytes):
    cfg = dataclasses.replace(load_config()["exr"], raw_table=f"{schema}.exr")
    runs = f"{schema}.pipeline_runs"
    wm = WatermarkStore(store)
    m = run_extract(cfg, client=api_client(fixture_bytes), store=store, watermarks=wm, now=NOW)
    run_load(cfg, m, conn=conn, store=store, watermarks=wm, runs_table=runs)
    before = snapshot(conn, cfg.raw_table)

    corrupt = dataclasses.replace(m, rows_extracted=999)  # manifest disagrees with the file
    with pytest.raises(LoadError):
        run_load(cfg, corrupt, conn=conn, store=store, watermarks=wm, runs_table=runs)
    assert snapshot(conn, cfg.raw_table) == before  # nothing deleted
    last = conn.execute(f"select status, error from {runs} order by run_pk desc limit 1").fetchone()
    assert last[0] == "failed" and "999" in last[1]


def test_record_dag_run_sums_dataset_loads_and_is_idempotent(conn, schema, store, fixture_bytes):
    cfg = dataclasses.replace(load_config()["exr"], raw_table=f"{schema}.exr")
    runs = f"{schema}.pipeline_runs"
    wm = WatermarkStore(store)
    m = run_extract(cfg, client=api_client(fixture_bytes), store=store, watermarks=wm, now=NOW)
    run_load(cfg, m, conn=conn, store=store, watermarks=wm, dag_run_id="dr-1", runs_table=runs)
    for _ in range(2):
        assert record_dag_run(conn, dag_run_id="dr-1", started_at=NOW, runs_table=runs) == 110
    rows = conn.execute(f"select mode, rows_loaded from {runs} where dataset = 'all'").fetchall()
    assert rows == [("dag_run", 110)]
