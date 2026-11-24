import importlib.util
import re
import sys

from tests.conftest import ROOT

_spec = importlib.util.spec_from_file_location("metabase_setup", ROOT / "scripts/metabase_setup.py")
mb = importlib.util.module_from_spec(_spec)
sys.modules["metabase_setup"] = mb  # dataclasses resolve their module via sys.modules
_spec.loader.exec_module(mb)

SAMPLE = """
### Q1.1 FX change
<!-- card: display=bar x=currency_code y=ytd_change_pct,mtd_change_pct row=0 col=12 w=12 h=6 -->
```sql
select currency_code, ytd_change_pct, mtd_change_pct
from marts.mart_fx_performance
```

### Q4.1 Freshness
<!-- card: display=scalar row=26 col=0 w=6 h=4 -->
```sql
select 1 as x
```
"""


def test_parse_cards_with_layout_and_chart_settings():
    cards = mb.parse_dashboard_md(SAMPLE)
    assert [c.name for c in cards] == ["Q1.1 FX change", "Q4.1 Freshness"]
    bar = cards[0]
    assert (bar.display, bar.x, bar.y, bar.row, bar.col, bar.w, bar.h) == (
        "bar", "currency_code", ["ytd_change_pct", "mtd_change_pct"], 0, 12, 12, 6,
    )  # fmt: skip
    assert bar.sql.startswith("select currency_code") and "```" not in bar.sql
    assert bar.visualization_settings() == {
        "graph.dimensions": ["currency_code"],
        "graph.metrics": ["ytd_change_pct", "mtd_change_pct"],
    }
    assert cards[1].visualization_settings() == {}
    line = mb.Card(name="l", sql="select 1", display="line", x="d", y=["v"])
    assert line.visualization_settings()["graph.y_axis.unpin_from_zero"] is True


def test_real_dashboard_doc_covers_q1_to_q4_and_reads_marts_only():
    cards = mb.parse_dashboard_md((ROOT / "docs/dashboard.md").read_text(encoding="utf-8"))
    assert {c.name.split(".")[0].split()[0] for c in cards} == {"Q1", "Q2", "Q3", "Q4"}
    for c in cards:
        schemas = set(re.findall(r"\b(raw|staging|intermediate|ops|snapshots|marts)\.", c.sql))
        assert schemas == {"marts"}, (c.name, schemas)
        assert c.col + c.w <= 24, c.name  # Metabase grid is 24 columns wide
