# ecb-markets-warehouse. Recipes avoid shell-specific syntax so they work from PowerShell, Git Bash and Linux CI.
# Windows: install GNU make with `scoop install make` (or `winget install GnuWin32.Make`).

ifeq ($(OS),Windows_NT)
VENV_BIN := .venv/Scripts
else
VENV_BIN := .venv/bin
endif
PY := $(VENV_BIN)/python
# Git Bash would rewrite container paths like /opt/... into C:/Program Files/Git/opt/...
export MSYS_NO_PATHCONV := 1
COMPOSE := docker compose
# Commands run inside the Airflow scheduler container (LocalExecutor: tasks run there too).
AF := $(COMPOSE) exec -T airflow-scheduler
PIPE := /opt/pipeline-venv/bin
DBT := $(AF) $(PIPE)/dbt
DAG := ecb_daily
-include .env
WAREHOUSE_USER ?= warehouse
WAREHOUSE_DB ?= warehouse
PSQL := $(COMPOSE) exec -T postgres psql -v ON_ERROR_STOP=1 -U $(WAREHOUSE_USER) -d $(WAREHOUSE_DB)

.PHONY: help env venv build up down logs ps stats psql migrate test test-integration lint format \
        demo dbt-build dbt-docs docs-check dashboard dashboard-screenshot freshness dag-test trigger backfill checksum benchmark clean

help:
	@echo "make up | down | logs | psql | test | lint | dbt-build | backfill START=YYYY-MM-DD END=YYYY-MM-DD"
	@echo "extras: venv build ps migrate test-integration format dbt-docs freshness dag-test trigger checksum benchmark"

env:
	$(if $(wildcard .env),@echo ".env present",$(error .env missing: run  cp .env.example .env))

venv:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip==25.3
	$(PY) -m pip install -e ".[dev]"

build: env
	$(COMPOSE) build

## Start the stack and block until every service is healthy.
up: env
	$(COMPOSE) up -d --build --wait --wait-timeout 600
	$(COMPOSE) ps

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

## Current CPU / memory per container.
stats:
	docker stats --no-stream --format "table {{.Name}}	{{.CPUPerc}}	{{.MemUsage}}"

psql:
	$(COMPOSE) exec postgres psql -U $(WAREHOUSE_USER) -d $(WAREHOUSE_DB)

## Re-apply the idempotent warehouse DDL (sql/init/ddl) to a running stack.
migrate:
	$(COMPOSE) exec -T postgres bash /docker-entrypoint-initdb.d/ddl/apply_ddl.sh

test:
	$(PY) -m pytest

## Integration tests need the stack running (make up).
test-integration:
	$(PY) -m pytest -m integration

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m sqlfluff lint dbt/ecb_warehouse/models dbt/ecb_warehouse/tests dbt/ecb_warehouse/snapshots scripts sql

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .
	$(PY) -m sqlfluff fix dbt/ecb_warehouse/models dbt/ecb_warehouse/tests scripts sql

dbt-build:
	$(DBT) build --project-dir /opt/project/dbt/ecb_warehouse

dbt-docs:
	$(DBT) docs generate --project-dir /opt/project/dbt/ecb_warehouse

## dbt docs + check that every model/source/column is documented and lineage is complete.
docs-check: dbt-docs
	$(AF) $(PIPE)/python /opt/project/scripts/check_dbt_docs.py /opt/airflow/dbt-target

## Create/update the Metabase dashboard from docs/dashboard.md (admin + read-only connection on first run).
dashboard:
	$(AF) env METABASE_URL=http://metabase:3000 METABASE_DISPLAY_URL=http://localhost:$(METABASE_PORT) $(PIPE)/python /opt/project/scripts/metabase_setup.py

## Re-render docs/img/dashboard.png (headless Chrome/Edge via a public dashboard link).
dashboard-screenshot:
	$(PY) scripts/dashboard_screenshot.py

freshness:
	$(DBT) source freshness --project-dir /opt/project/dbt/ecb_warehouse

## Parse the DAG and report import errors.
dag-test:
	$(AF) airflow dags reserialize
	$(AF) airflow dags list-import-errors
	$(AF) airflow dags list
	$(AF) python /opt/project/tests/dags/test_ecb_daily.py

## Run the DAG once now (incremental; the very first run loads full history) and wait for the result.
trigger:
	$(AF) bash /opt/project/scripts/run_dag.sh

## Quick start step 3: first run (full history) + Metabase dashboard.
demo: trigger dashboard
	@echo "Airflow  http://localhost:$(AIRFLOW_PORT)   (user $(AIRFLOW_ADMIN_USER), password in .env)"
	@echo "Metabase http://localhost:$(METABASE_PORT)  (user $(METABASE_ADMIN_EMAIL), password in .env)"

## Manual backfill: re-extract an observation range for every dataset (watermarks untouched).
backfill:
	$(if $(START),,$(error usage: make backfill START=YYYY-MM-DD END=YYYY-MM-DD))
	$(if $(END),,$(error usage: make backfill START=YYYY-MM-DD END=YYYY-MM-DD))
	$(AF) bash /opt/project/scripts/run_dag.sh "{\"start\": \"$(START)\", \"end\": \"$(END)\"}"

## Idempotency proof (spec §7): row count + checksum of fct_fx_rate_daily.
checksum:
	$(PSQL) -f /opt/scripts/checksum.sql

## Run-time statistics computed from ops.pipeline_runs (the only allowed source of numbers).
benchmark:
	$(PSQL) -f /opt/scripts/benchmark.sql

clean:
	$(COMPOSE) down -v
