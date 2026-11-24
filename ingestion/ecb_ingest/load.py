"""Load one landed file from S3 into Postgres raw.<dataset> (FR-04) and log it (FR-09).

Idempotent per load_id: inside ONE transaction we delete the load_id's rows, COPY the file's rows and write the
ops.pipeline_runs row. Re-running a load_id therefore yields exactly the same raw rows. The watermark is
advanced only after that transaction committed (FR-02).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql

from ecb_ingest.config import DatasetConfig
from ecb_ingest.extract import Manifest, manifest_key
from ecb_ingest.parsing import parse_csv, select_columns
from ecb_ingest.s3 import S3Store
from ecb_ingest.state import WatermarkStore

log = logging.getLogger(__name__)

META_COLUMNS = ("load_id", "row_num", "extracted_at", "source_url", "s3_key")
RUNS_TABLE = "ops.pipeline_runs"


class LoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadResult:
    dataset: str
    load_id: str
    status: str
    rows_extracted: int
    rows_loaded: int
    watermark_advanced: bool


def _qualified(name: str) -> sql.Composed:
    schema, _, table = name.partition(".")
    return sql.SQL(".").join([sql.Identifier(schema), sql.Identifier(table)])


def read_manifest(store: S3Store, dataset: str, load_id: str) -> Manifest:
    body = store.get_bytes(manifest_key(dataset, load_id))
    if body is None:
        raise LoadError(f"no manifest for {dataset}/{load_id}; run extract first")
    return Manifest.from_json(body)


def build_rows(cfg: DatasetConfig, manifest: Manifest, body: bytes | None) -> list[list[Any]]:
    """Rows for COPY: configured columns (config order) + metadata columns (META_COLUMNS order)."""
    if not body:
        return []
    header, rows = parse_csv(body)
    if not rows:
        return []
    projected = select_columns(cfg, header, rows)
    extracted_at = datetime.fromisoformat(manifest.request_started_at)
    return [
        [*values, manifest.load_id, i, extracted_at, manifest.source_url, manifest.s3_key]
        for i, values in enumerate(projected, start=1)
    ]


def _insert_run(
    cur: psycopg.Cursor,
    manifest: Manifest,
    *,
    status: str,
    rows_loaded: int,
    finished_at: datetime,
    dag_run_id: str | None,
    error: str | None = None,
    runs_table: str = RUNS_TABLE,
) -> None:
    cur.execute(
        sql.SQL(
            "insert into {} (dataset, load_id, mode, dag_run_id, rows_extracted, rows_loaded, started_at, "
            "finished_at, status, error, s3_key, source_url) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        ).format(_qualified(runs_table)),
        (
            manifest.dataset,
            manifest.load_id,
            manifest.mode,
            dag_run_id or manifest.run_id,
            manifest.rows_extracted,
            rows_loaded,
            datetime.fromisoformat(manifest.request_started_at),
            finished_at,
            status,
            error,
            manifest.s3_key,
            manifest.source_url,
        ),
    )


def run_load(
    cfg: DatasetConfig,
    manifest: Manifest,
    *,
    conn: psycopg.Connection,
    store: S3Store,
    watermarks: WatermarkStore,
    dag_run_id: str | None = None,
    runs_table: str = RUNS_TABLE,
) -> LoadResult:
    if manifest.dataset != cfg.name:
        raise LoadError(f"manifest is for {manifest.dataset}, not {cfg.name}")
    table = _qualified(cfg.raw_table)
    columns = [*cfg.columns.values(), *META_COLUMNS]
    try:
        body = store.get_bytes(manifest.s3_key) if manifest.s3_key else None
        if manifest.s3_key and body is None:
            raise LoadError(f"landed object s3://{store.bucket}/{manifest.s3_key} is missing")
        rows = build_rows(cfg, manifest, body)
        if len(rows) != manifest.rows_extracted:
            raise LoadError(f"{manifest.load_id}: file has {len(rows)} rows, manifest says {manifest.rows_extracted}")

        with conn.transaction(), conn.cursor() as cur:
            cur.execute(sql.SQL("delete from {} where load_id = %s").format(table), (manifest.load_id,))
            replaced = cur.rowcount
            copy_stmt = sql.SQL("copy {} ({}) from stdin").format(
                table, sql.SQL(", ").join(map(sql.Identifier, columns))
            )
            with cur.copy(copy_stmt) as copy:
                for row in rows:
                    copy.write_row(row)
            cur.execute(sql.SQL("select count(*) from {} where load_id = %s").format(table), (manifest.load_id,))
            rows_loaded = int(cur.fetchone()[0])
            if rows_loaded != len(rows):
                raise LoadError(f"{manifest.load_id}: copied {len(rows)} rows but found {rows_loaded}")
            status = "success" if rows_loaded > 0 else "no_data"
            _insert_run(
                cur,
                manifest,
                status=status,
                rows_loaded=rows_loaded,
                finished_at=datetime.now(UTC),
                dag_run_id=dag_run_id,
                runs_table=runs_table,
            )
    except Exception as exc:
        _record_failure(conn, manifest, exc, dag_run_id, runs_table)
        raise

    advanced = False
    if manifest.watermark_candidate:
        advanced = watermarks.advance(cfg.name, manifest.watermark_candidate, manifest.load_id)
    log.info(
        "%s: loaded %s rows into %s (replaced %s), status=%s, watermark advanced=%s",
        manifest.load_id,
        rows_loaded,
        cfg.raw_table,
        replaced,
        status,
        advanced,
    )
    return LoadResult(cfg.name, manifest.load_id, status, manifest.rows_extracted, rows_loaded, advanced)


def _record_failure(
    conn: psycopg.Connection, manifest: Manifest, exc: Exception, dag_run_id: str | None, runs_table: str
) -> None:
    try:
        with conn.transaction(), conn.cursor() as cur:
            _insert_run(
                cur,
                manifest,
                status="failed",
                rows_loaded=0,
                finished_at=datetime.now(UTC),
                dag_run_id=dag_run_id,
                error=f"{type(exc).__name__}: {exc}"[:2000],
                runs_table=runs_table,
            )
    except Exception:  # never mask the original error
        log.exception("could not record failed run for %s", manifest.load_id)


def record_dag_run(
    conn: psycopg.Connection,
    *,
    dag_run_id: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    runs_table: str = RUNS_TABLE,
) -> int:
    """Write one 'all' row summarising a fully successful DAG run (used for run-time statistics)."""
    finished_at = finished_at or datetime.now(UTC)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "select coalesce(sum(rows_extracted), 0), coalesce(sum(rows_loaded), 0) from {} "
                "where dag_run_id = %s and dataset <> 'all' and status <> 'failed'"
            ).format(_qualified(runs_table)),
            (dag_run_id,),
        )
        extracted, loaded = cur.fetchone()
        cur.execute(sql.SQL("delete from {} where dataset = 'all' and load_id = %s").format(_qualified(runs_table)),
                    (dag_run_id,))  # fmt: skip
        cur.execute(
            sql.SQL(
                "insert into {} (dataset, load_id, mode, dag_run_id, rows_extracted, rows_loaded, started_at, "
                "finished_at, status) values ('all', %s, 'dag_run', %s, %s, %s, %s, %s, 'success')"
            ).format(_qualified(runs_table)),
            (dag_run_id, dag_run_id, extracted, loaded, started_at, finished_at),
        )
    return int(loaded)
