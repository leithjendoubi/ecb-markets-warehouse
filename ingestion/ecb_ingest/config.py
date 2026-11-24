"""Load and validate config.yaml (FR-01: config-driven extraction)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    flow: str
    key: str
    start_period: str
    raw_table: str
    columns: dict[str, str]  # CSV column -> raw column
    required: tuple[str, ...]
    format: str = "csvdata"
    description: str = ""

    @property
    def raw_schema(self) -> str:
        return self.raw_table.split(".", 1)[0]

    @property
    def raw_name(self) -> str:
        return self.raw_table.split(".", 1)[1]


def _parse(doc: dict[str, Any]) -> dict[str, DatasetConfig]:
    defaults = doc.get("defaults", {})
    out: dict[str, DatasetConfig] = {}
    for name, raw in doc["datasets"].items():
        cfg = DatasetConfig(
            name=name,
            flow=str(raw["flow"]),
            key=str(raw["key"]),
            start_period=str(raw["start_period"]),
            raw_table=str(raw["raw_table"]),
            columns={str(k): str(v) for k, v in raw["columns"].items()},
            required=tuple(raw.get("required", defaults.get("required", []))),
            format=str(raw.get("format", defaults.get("format", "csvdata"))),
            description=str(raw.get("description", "")),
        )
        _validate(cfg)
        out[name] = cfg
    return out


def _validate(cfg: DatasetConfig) -> None:
    schema, _, table = cfg.raw_table.partition(".")
    if not (_IDENT.match(schema) and _IDENT.match(table)):
        raise ValueError(f"{cfg.name}: raw_table must be schema.table in snake_case, got {cfg.raw_table!r}")
    for target in cfg.columns.values():
        if not _IDENT.match(target):
            raise ValueError(f"{cfg.name}: raw column {target!r} is not snake_case")
    missing = [c for c in cfg.required if c not in cfg.columns]
    if missing:
        raise ValueError(f"{cfg.name}: required columns {missing} are not mapped in `columns`")
    if not re.fullmatch(r"[A-Za-z0-9_.+]+", cfg.key):
        raise ValueError(f"{cfg.name}: unexpected characters in series key {cfg.key!r}")


def load_config(path: str | Path | None = None) -> dict[str, DatasetConfig]:
    if path is None:
        text = resources.files("ecb_ingest").joinpath("config.yaml").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    return _parse(yaml.safe_load(text))
