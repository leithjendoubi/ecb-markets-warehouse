#!/usr/bin/env bash
# Trigger ecb_daily and block until the run finishes (runs inside the Airflow scheduler container).
# Usage: run_dag.sh [conf-json]      e.g. run_dag.sh '{"start": "2024-01-01", "end": "2024-12-31"}'
# Exit code 0 = run succeeded, 1 = failed/timeout.
set -euo pipefail
dag=ecb_daily
conf="${1:-}"
run_id="make__$(date -u +%Y%m%dT%H%M%SZ)"
airflow dags unpause "$dag" > /dev/null
if [[ -n "$conf" ]]; then
  airflow dags trigger "$dag" --run-id "$run_id" --conf "$conf" > /dev/null
else
  airflow dags trigger "$dag" --run-id "$run_id" > /dev/null
fi
echo "triggered $dag run $run_id ${conf:+with conf $conf}"
for _ in $(seq 1 360); do
  state=$(airflow dags list-runs "$dag" -o json 2>/dev/null \
    | python -c "import json,sys; r=[x for x in json.load(sys.stdin) if x['run_id']=='$run_id']; print(r[0]['state'] if r else 'missing')")
  case "$state" in
    success) echo "$run_id: success"; exit 0 ;;
    failed) echo "$run_id: FAILED - see the Airflow UI (http://localhost:8080) task logs" >&2; exit 1 ;;
  esac
  sleep 5
done
echo "$run_id: still '$state' after 30 min" >&2
exit 1
