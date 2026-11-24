import importlib.util

from tests.conftest import ROOT

_spec = importlib.util.spec_from_file_location("check_dbt_docs", ROOT / "scripts/check_dbt_docs.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def _manifest(description="A model", col_desc="key", deps=("source.p.raw.exr",)):
    return {
        "metadata": {"project_name": "p"},
        "nodes": {
            "model.p.m": {
                "resource_type": "model", "name": "m", "package_name": "p", "description": description,
                "columns": {"id": {"description": col_desc}}, "depends_on": {"nodes": list(deps)},
            }
        },
        "sources": {
            "source.p.raw.exr": {
                "resource_type": "source", "name": "exr", "package_name": "p", "description": "raw", "columns": {},
            }
        },
    }  # fmt: skip


CATALOG = {"nodes": {"model.p.m": {"columns": {"id": {}}}}, "sources": {}}


def test_fully_documented_project_passes():
    assert check.find_problems(_manifest(), CATALOG) == []


def test_missing_model_description_fails():
    assert check.find_problems(_manifest(description=""), CATALOG) == ["model m: missing description"]


def test_undocumented_database_column_fails():
    catalog = {"nodes": {"model.p.m": {"columns": {"id": {}, "extra": {}}}}, "sources": {}}
    assert check.find_problems(_manifest(), catalog) == ["model m: column extra not documented"]


def test_model_without_parents_fails():
    assert check.find_problems(_manifest(deps=()), CATALOG) == ["model m: no upstream nodes (broken lineage)"]
