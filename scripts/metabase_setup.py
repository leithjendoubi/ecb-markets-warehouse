"""Create/update the Metabase dashboard from docs/dashboard.md via the Metabase REST API (idempotent).

    python scripts/metabase_setup.py            # make dashboard
    python scripts/metabase_setup.py --public   # also enable a public link (used for the screenshot)

Steps: first-run setup (admin user from .env) -> warehouse connection as the read-only user (marts only)
-> one native SQL question per `###` card in docs/dashboard.md -> dashboard layout -> run every card once
and fail if any query errors. Prints the dashboard URL (and the public URL with --public) on the last line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_MD = ROOT / "docs/dashboard.md"
DASHBOARD_NAME = "ECB Markets Warehouse"
DATABASE_NAME = "ECB Warehouse (marts)"

_CARD = re.compile(
    r"^###\s+(?P<name>.+?)\s*\n<!--\s*card:\s*(?P<meta>.*?)\s*-->\s*\n```sql\n(?P<sql>.*?)```", re.M | re.S
)


@dataclass
class Card:
    name: str
    sql: str
    display: str = "table"
    x: str | None = None
    y: list[str] = field(default_factory=list)
    row: int = 0
    col: int = 0
    w: int = 12
    h: int = 6

    def visualization_settings(self) -> dict:
        if self.display in {"line", "bar"} and self.x:
            settings: dict = {"graph.dimensions": [self.x], "graph.metrics": self.y}
            if self.display == "line":
                settings["graph.y_axis.unpin_from_zero"] = True  # FX levels near 1.0 look flat from zero
            return settings
        return {}


def parse_dashboard_md(text: str) -> list[Card]:
    cards = []
    for m in _CARD.finditer(text):
        meta = dict(kv.split("=", 1) for kv in m.group("meta").split())
        cards.append(
            Card(
                name=m.group("name").strip(),
                sql=m.group("sql").strip(),
                display=meta.get("display", "table"),
                x=meta.get("x"),
                y=[v for v in meta.get("y", "").split(",") if v],
                row=int(meta.get("row", 0)),
                col=int(meta.get("col", 0)),
                w=int(meta.get("w", 12)),
                h=int(meta.get("h", 6)),
            )
        )
    return cards


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines from .env into os.environ (existing variables win). No extra dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set (see .env.example)")
    return value


class Metabase:
    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=120)

    def call(self, method: str, path: str, **kw) -> dict | list:
        resp = self.http.request(method, path, **kw)
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json() if resp.content else {}

    def login_or_setup(self, email: str, password: str) -> None:
        props = self.call("GET", "/api/session/properties")
        if not props.get("has-user-setup"):
            self.call(
                "POST",
                "/api/setup",
                json={
                    "token": props["setup-token"],
                    "user": {"email": email, "password": password, "first_name": "Admin", "last_name": "Local",
                             "site_name": "ECB Markets Warehouse"},
                    "prefs": {"site_name": "ECB Markets Warehouse", "allow_tracking": False},
                },
            )  # fmt: skip
            print("metabase: initial setup done", file=sys.stderr)
        session = self.call("POST", "/api/session", json={"username": email, "password": password})
        self.http.headers["X-Metabase-Session"] = session["id"]

    def ensure_database(self) -> int:
        details = {
            "host": os.environ.get("METABASE_WAREHOUSE_HOST", "postgres"),
            "port": 5432,
            "dbname": _env("WAREHOUSE_DB"),
            "user": _env("WAREHOUSE_RO_USER"),
            "password": _env("WAREHOUSE_RO_PASSWORD"),
            "ssl": False,
            "schema-filters-type": "inclusion",
            "schema-filters-patterns": "marts",
        }
        dbs = self.call("GET", "/api/database")
        dbs = dbs.get("data", dbs) if isinstance(dbs, dict) else dbs
        for db in dbs:
            if db["name"] == DATABASE_NAME:
                self.call("PUT", f"/api/database/{db['id']}", json={"details": details})
                return int(db["id"])
        db = self.call("POST", "/api/database", json={"engine": "postgres", "name": DATABASE_NAME, "details": details})
        return int(db["id"])

    def ensure_collection(self) -> int:
        for c in self.call("GET", "/api/collection"):
            if c.get("name") == DASHBOARD_NAME and not c.get("archived"):
                return int(c["id"])
        return int(self.call("POST", "/api/collection", json={"name": DASHBOARD_NAME, "color": "#509EE3"})["id"])

    def upsert_card(self, card: Card, db_id: int, collection_id: int) -> int:
        body = {
            "name": card.name,
            "display": card.display,
            "collection_id": collection_id,
            "visualization_settings": card.visualization_settings(),
            "dataset_query": {"type": "native", "native": {"query": card.sql}, "database": db_id},
        }
        existing = [
            c for c in self.call("GET", "/api/card", params={"f": "all"})
            if c["name"] == card.name and c.get("collection_id") == collection_id and not c.get("archived")
        ]  # fmt: skip
        if existing:
            self.call("PUT", f"/api/card/{existing[0]['id']}", json=body)
            return int(existing[0]["id"])
        return int(self.call("POST", "/api/card", json=body)["id"])

    def check_card(self, card_id: int, name: str) -> int:
        res = self.call("POST", f"/api/card/{card_id}/query")
        if res.get("status") != "completed" or res.get("error"):
            raise RuntimeError(f"card {name!r} failed: {res.get('error')}")
        return int(res.get("row_count", 0))

    def upsert_dashboard(self, cards: list[tuple[int, Card]], collection_id: int) -> int:
        dash_id = None
        for d in self.call("GET", "/api/dashboard", params={"f": "all"}):
            if d["name"] == DASHBOARD_NAME and not d.get("archived"):
                dash_id = int(d["id"])
        if dash_id is None:
            dash_id = int(
                self.call(
                    "POST",
                    "/api/dashboard",
                    json={"name": DASHBOARD_NAME, "collection_id": collection_id,
                          "description": "Q1-Q4 from docs/dashboard.md (generated by scripts/metabase_setup.py)"},
                )["id"]
            )  # fmt: skip
        dashcards = [
            {"id": -(i + 1), "card_id": cid, "row": c.row, "col": c.col, "size_x": c.w, "size_y": c.h,
             "parameter_mappings": [], "visualization_settings": {}}
            for i, (cid, c) in enumerate(cards)
        ]  # fmt: skip
        self.call("PUT", f"/api/dashboard/{dash_id}", json={"dashcards": dashcards})
        return dash_id

    def public_link(self, dash_id: int) -> str:
        self.call("PUT", "/api/setting/enable-public-sharing", json={"value": True})
        return str(self.call("POST", f"/api/dashboard/{dash_id}/public_link")["uuid"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", action="store_true", help="enable and print a public dashboard link")
    args = parser.parse_args(argv)
    load_dotenv()

    base = os.environ.get("METABASE_URL", f"http://localhost:{os.environ.get('METABASE_PORT', '3000')}")
    cards = parse_dashboard_md(DASHBOARD_MD.read_text(encoding="utf-8"))
    if not cards:
        raise SystemExit("no cards found in docs/dashboard.md")
    mb = Metabase(base)
    mb.login_or_setup(_env("METABASE_ADMIN_EMAIL"), _env("METABASE_ADMIN_PASSWORD"))
    db_id = mb.ensure_database()
    collection_id = mb.ensure_collection()
    placed = []
    for card in cards:
        cid = mb.upsert_card(card, db_id, collection_id)
        rows = mb.check_card(cid, card.name)
        print(f"card ok ({rows} rows): {card.name}", file=sys.stderr)
        placed.append((cid, card))
    dash_id = mb.upsert_dashboard(placed, collection_id)
    result = {"dashboard_url": f"{base}/dashboard/{dash_id}", "cards": len(placed)}
    if args.public:
        result["public_url"] = f"{base}/public/dashboard/{mb.public_link(dash_id)}"
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
