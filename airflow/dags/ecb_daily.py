"""ecb_daily: ECB Data Portal -> S3 raw -> Postgres raw.* -> dbt build -> source freshness (spec §4, FR-08).

Schedule: Mon-Fri 18:00 Europe/Berlin (ECB reference rates are published around 16:00 CET).
Normal run:  incremental per dataset (updatedAfter = watermark; first run = full history).
Backfill:    trigger with params {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} (make backfill START=.. END=..);
             re-extracts that observation range for every dataset and leaves the watermarks untouched.

Every task shells out to the pipeline venv (docs/decisions/0001-pipeline-venv-in-airflow-image.md).
The load task is serialised (one at a time) because loads share the watermark document (ADR 0002).
"""

from __future__ import annotations

import json
import shlex
from datetime import timedelta

import pendulum
from airflow.sdk import CronTriggerTimetable, Param, dag, task

DATASETS = ["exr", "est", "fm", "hicp"]
PY = "/opt/pipeline-venv/bin/python -m ecb_ingest.cli"
DBT = "/opt/pipeline-venv/bin/dbt"
DBT_DIR = "/opt/project/dbt/ecb_warehouse"

default_args = {
    "owner": "data-eng",
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
}


def _q(value: object) -> str:
    return shlex.quote(str(value))


@dag(
    dag_id="ecb_daily",
    description="ECB FX, EUR STR, key rates and HICP into a tested star schema",
    schedule=CronTriggerTimetable("0 18 * * 1-5", timezone="Europe/Berlin"),
    start_date=pendulum.datetime(2026, 11, 2, tz="Europe/Berlin"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    dagrun_timeout=timedelta(hours=2),
    params={
        "start": Param(
            None, type=["null", "string"], format="date", description="Backfill start YYYY-MM-DD (empty = incremental)"
        ),
        "end": Param(None, type=["null", "string"], format="date", description="Backfill end YYYY-MM-DD"),
    },
    tags=["ecb", "elt"],
)
def ecb_daily():
    @task.bash
    def extract(dataset: str, params: dict | None = None, run_id: str | None = None) -> str:
        params = params or {}
        start, end = params.get("start"), params.get("end")
        if bool(start) != bool(end):
            raise ValueError("backfill needs both 'start' and 'end'")
        cmd = f"{PY} extract --dataset {_q(dataset)} --run-id {_q(run_id)}"
        if start:
            cmd += f" --start {_q(start)} --end {_q(end)}"
        return cmd

    @task.bash(max_active_tis_per_dagrun=1)
    def load(extract_result: str, run_id: str | None = None) -> str:
        result = json.loads(extract_result)
        return f"{PY} load --dataset {_q(result['dataset'])} --load-id {_q(result['load_id'])} --run-id {_q(run_id)}"

    @task.bash
    def dbt_build() -> str:
        return f"cd {DBT_DIR} && {DBT} build"

    @task.bash
    def dbt_source_freshness() -> str:
        return f"cd {DBT_DIR} && {DBT} source freshness"

    @task.bash
    def record_run(run_id: str | None = None, dag_run=None) -> str:
        started_at = dag_run.start_date.isoformat()
        return f"{PY} record-run --run-id {_q(run_id)} --started-at {_q(started_at)}"

    loaded = load.expand(extract_result=extract.expand(dataset=DATASETS))
    loaded >> dbt_build() >> dbt_source_freshness() >> record_run()


ecb_daily()
