#!/usr/bin/env bash
# Apply every warehouse DDL file in order. All files are idempotent (create ... if not exists).
# Called by sql/init/00_init.sh on first start, and by `make migrate` on a running stack.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
for f in "$here"/*.sql; do
  echo "applying $f"
  psql -v ON_ERROR_STOP=1 --username "$WAREHOUSE_USER" --dbname "$WAREHOUSE_DB" \
       -v ro_user="$WAREHOUSE_RO_USER" -v owner="$WAREHOUSE_USER" -v dbname="$WAREHOUSE_DB" -f "$f"
done
