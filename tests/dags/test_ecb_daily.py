"""Structure tests for the ecb_daily DAG (FR-08).

Airflow does not run on Windows, so these run inside the Airflow container:  make dag-test
(plain asserts, no pytest needed there). On the host, tests/conftest.py skips this folder if Airflow is absent.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.dag_processing.dagbag import DagBag

DAGS_FOLDER = "/opt/airflow/dags"


def _dag():
    bag = DagBag(dag_folder=DAGS_FOLDER)
    assert not bag.import_errors, bag.import_errors
    return bag.get_dag("ecb_daily")


def test_schedule_and_run_policy():
    dag = _dag()
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    tt = dag.timetable
    assert tt.expression == "0 18 * * 1-5", tt  # Mon-Fri 18:00
    assert str(tt.timezone) == "Europe/Berlin", tt


def test_retries_with_exponential_backoff():
    for t in _dag().tasks:
        assert t.retries == 3, t.task_id
        assert t.retry_exponential_backoff, t.task_id
        assert t.retry_delay == timedelta(minutes=1)


def test_task_graph_is_extract_load_dbt_freshness_record():
    dag = _dag()
    ids = {t.task_id for t in dag.tasks}
    assert ids == {"extract", "load", "dbt_build", "dbt_source_freshness", "record_run"}
    assert dag.get_task("load").upstream_task_ids == {"extract"}
    assert dag.get_task("dbt_build").upstream_task_ids == {"load"}
    assert dag.get_task("dbt_source_freshness").upstream_task_ids == {"dbt_build"}
    assert dag.get_task("record_run").upstream_task_ids == {"dbt_source_freshness"}


def test_extract_and_load_are_mapped_and_loads_serialised():
    dag = _dag()
    extract, load = dag.get_task("extract"), dag.get_task("load")
    assert extract.is_mapped and load.is_mapped  # dynamic task mapping, one instance per dataset
    assert load.max_active_tis_per_dagrun == 1


def test_backfill_params():
    params = _dag().params
    assert "start" in params and "end" in params
    assert params["start"] is None and params["end"] is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(tests)} DAG tests passed")
