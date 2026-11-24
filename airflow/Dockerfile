# Airflow 3.4 image + an isolated venv for the pipeline (ingestion package deps + dbt).
# The venv keeps dbt/boto3/httpx pins (pyproject.toml) independent of Airflow's own constraints.
FROM apache/airflow:3.4.0-python3.12

USER root
RUN python -m venv /opt/pipeline-venv && chown -R airflow:0 /opt/pipeline-venv

USER airflow
COPY --chown=airflow:0 pyproject.toml /tmp/build/pyproject.toml
COPY --chown=airflow:0 ingestion /tmp/build/ingestion
# PIP_USER=false: the base image sets PIP_USER=true, which is invalid inside a venv.
RUN PIP_USER=false /opt/pipeline-venv/bin/pip install --no-cache-dir /tmp/build \
    && rm -rf /tmp/build \
    && /opt/pipeline-venv/bin/dbt --version
# Source is bind-mounted at /opt/project and put first on PYTHONPATH (docker-compose.yml),
# so code edits take effect without rebuilding; rebuild only when pins change.
