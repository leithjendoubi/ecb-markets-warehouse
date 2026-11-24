import re
from datetime import UTC, datetime

import yaml

from ecb_ingest.config import load_config
from ecb_ingest.extract import Manifest
from ecb_ingest.load import META_COLUMNS, build_rows
from tests.conftest import ROOT


def manifest(**kw):
    base = dict(
        dataset="exr", load_id="exr-full-20261124T170500Z", mode="full", source_url="https://x/data/EXR/k",
        http_status=200, s3_key="raw/ecb/exr/ingestion_date=2026-11-24/exr-full-20261124T170500Z.csv",
        rows_extracted=110, request_started_at="2026-11-24T17:05:00+00:00", ingestion_date="2026-11-24",
        watermark_before=None, watermark_candidate="2026-11-24T17:05:00+00:00", start_period="2015-01-01",
        end_period=None,
    )  # fmt: skip
    base.update(kw)
    return Manifest(**base)


def test_build_rows_appends_metadata(fixture_bytes):
    cfg = load_config()["exr"]
    rows = build_rows(cfg, manifest(), fixture_bytes("exr_sample.csv"))
    assert len(rows) == 110
    n = len(cfg.columns)
    assert len(rows[0]) == n + len(META_COLUMNS)
    meta = dict(zip(META_COLUMNS, rows[0][n:], strict=True))
    assert meta["load_id"] == "exr-full-20261124T170500Z"
    assert meta["row_num"] == 1 and rows[-1][n + 1] == 110
    assert meta["extracted_at"] == datetime(2026, 11, 24, 17, 5, tzinfo=UTC)


def test_build_rows_empty_for_no_data():
    assert build_rows(load_config()["exr"], manifest(s3_key=None, rows_extracted=0), None) == []


def _ddl_columns(table: str) -> list[str]:
    ddl = (ROOT / "sql/init/ddl/02_raw.sql").read_text(encoding="utf-8")
    body = re.search(rf"create table if not exists {re.escape(table)} \((.*?)\n\);", ddl, re.S)
    assert body, f"{table} missing in 02_raw.sql"
    cols = []
    for line in body.group(1).strip().splitlines():
        first = line.strip().split()[0]
        if first != "constraint":
            cols.append(first)
    return cols


def test_raw_ddl_matches_config():
    for cfg in load_config().values():
        expected = [*cfg.columns.values(), *META_COLUMNS[:3], "ingested_at", *META_COLUMNS[3:]]
        assert _ddl_columns(cfg.raw_table) == expected, cfg.raw_table


def test_raw_columns_are_documented_in_dbt_sources():
    doc = yaml.safe_load((ROOT / "dbt/ecb_warehouse/models/staging/_sources.yml").read_text(encoding="utf-8"))
    raw = next(s for s in doc["sources"] if s["name"] == "raw")
    tables = {t["name"]: [c["name"] for c in t.get("columns", [])] for t in raw["tables"]}
    for name, cfg in load_config().items():
        expected = [*cfg.columns.values(), *META_COLUMNS[:3], "ingested_at", *META_COLUMNS[3:]]
        assert tables[name] == expected, name
