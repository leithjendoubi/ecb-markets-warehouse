# 0001: Pipeline code runs in its own venv inside the Airflow image

**Context.** Airflow 3.4 ships with its own constraint set (boto3, httpx, ...). dbt-core 1.12 and our pinned
ingestion dependencies (project rule: pin exact versions) would fight those constraints if installed into Airflow's
environment, and the host tests should run against the same versions as production.

**Decision.** `airflow/Dockerfile` creates `/opt/pipeline-venv` from `pyproject.toml` (the single source of pins).
Airflow tasks are `@task.bash` commands calling `/opt/pipeline-venv/bin/python -m ecb_ingest.cli ...` and
`/opt/pipeline-venv/bin/dbt ...`. Source code is bind-mounted and first on `PYTHONPATH`, so edits need no rebuild.
Only `airflow-init` builds the image; other services reuse it (parallel builds of one tag race).

**Consequences.** Airflow upgrades and pipeline upgrades are independent. Tasks exchange only small JSON via
the last stdout line (XCom); larger state lives in S3 manifests. Each task pays a separate Python start-up.
