"""Fail if the dbt project is not fully documented or has broken lineage (M5 "lineage complete").

Reads target/manifest.json and target/catalog.json (from `dbt docs generate`) and checks that
- every model, seed, snapshot and source has a description,
- every column that exists in the database (catalog) is documented in YAML,
- every model has at least one upstream node (so lineage reaches back to a source or seed).

    python scripts/check_dbt_docs.py <dbt target dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CHECKED = ("model", "seed", "snapshot")


def find_problems(manifest: dict, catalog: dict) -> list[str]:
    problems: list[str] = []
    cat_nodes = {**catalog.get("nodes", {}), **catalog.get("sources", {})}
    nodes = {k: v for k, v in manifest["nodes"].items() if v["resource_type"] in CHECKED}
    for uid, node in sorted({**nodes, **manifest.get("sources", {})}.items()):
        if node.get("package_name") != manifest["metadata"].get("project_name", node.get("package_name")):
            continue
        name = f"{node['resource_type']} {node['name']}"
        if not (node.get("description") or "").strip():
            problems.append(f"{name}: missing description")
        documented = {c.lower(): (v.get("description") or "").strip() for c, v in node.get("columns", {}).items()}
        for col in cat_nodes.get(uid, {}).get("columns", {}):
            if col.startswith("dbt_"):
                continue  # snapshot meta columns are documented by dbt itself
            if not documented.get(col.lower()):
                problems.append(f"{name}: column {col} not documented")
        if node["resource_type"] == "model" and not node.get("depends_on", {}).get("nodes"):
            problems.append(f"{name}: no upstream nodes (broken lineage)")
    return problems


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else "dbt/ecb_warehouse/target")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
    problems = find_problems(manifest, catalog)
    for p in problems:
        print(f"UNDOCUMENTED {p}")
    n = sum(1 for v in manifest["nodes"].values() if v["resource_type"] in CHECKED) + len(manifest.get("sources", {}))
    print(f"checked {n} nodes: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
