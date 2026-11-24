"""Parse ECB `format=csvdata` responses. Only columns that exist in the real responses are used."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable

from ecb_ingest.config import DatasetConfig

log = logging.getLogger(__name__)


class FormatError(ValueError):
    """The response does not look like the CSV we saved in tests/fixtures (API change?)."""


def parse_csv(body: bytes) -> tuple[list[str], list[list[str]]]:
    """Return (header, rows). The ECB sends UTF-8 with CRLF line endings and RFC 4180 quoting."""
    text = body.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    rows = [row for row in reader if row]
    for i, row in enumerate(rows, start=2):
        if len(row) != len(header):
            raise FormatError(f"line {i}: {len(row)} fields, header has {len(header)}")
    return header, rows


def check_header(cfg: DatasetConfig, header: Iterable[str]) -> list[str]:
    """Raise if a required column is missing; return configured-but-absent optional columns."""
    present = set(header)
    missing_required = [c for c in cfg.required if c not in present]
    if missing_required:
        raise FormatError(f"{cfg.name}: response lacks required columns {missing_required}")
    missing_optional = [c for c in cfg.columns if c not in present]
    if missing_optional:
        log.warning("%s: response lacks optional columns %s; loading NULL", cfg.name, missing_optional)
    return missing_optional


def select_columns(cfg: DatasetConfig, header: list[str], rows: list[list[str]]) -> list[list[str | None]]:
    """Project rows onto the configured columns (in config order). Empty strings become NULL."""
    check_header(cfg, header)
    index = {name: i for i, name in enumerate(header)}
    positions = [index.get(col) for col in cfg.columns]
    out: list[list[str | None]] = []
    for row in rows:
        out.append([(row[p] if row[p] != "" else None) if p is not None else None for p in positions])
    return out
