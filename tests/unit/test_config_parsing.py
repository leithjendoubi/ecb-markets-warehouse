import pytest

from ecb_ingest.config import load_config
from ecb_ingest.parsing import FormatError, parse_csv, select_columns

FIXTURE_FOR = {"exr": "exr_sample.csv", "est": "est_sample.csv", "fm": "fm_sample.csv", "hicp": "hicp_sample.csv"}


def test_config_has_the_four_spec_datasets():
    cfg = load_config()
    assert set(cfg) == {"exr", "est", "fm", "hicp"}
    assert cfg["exr"].key == "D.USD+GBP+CHF+JPY+CNY+SEK+NOK+PLN+CAD+AUD.EUR.SP00.A"
    assert cfg["exr"].start_period == "2015-01-01"
    assert cfg["est"].start_period == "2019-10-01"
    assert cfg["fm"].start_period == "1999-01-01"
    assert cfg["hicp"].flow == "HICP"  # ICP was replaced by HICP


@pytest.mark.parametrize("dataset", sorted(FIXTURE_FOR))
def test_every_configured_column_exists_in_the_real_response(dataset, fixture_bytes):
    """Never invent fields: every mapped column must be present in the saved API response."""
    cfg = load_config()[dataset]
    header, rows = parse_csv(fixture_bytes(FIXTURE_FOR[dataset]))
    assert rows
    assert [c for c in cfg.columns if c not in header] == []


def test_parse_exr_fixture(fixture_bytes):
    header, rows = parse_csv(fixture_bytes("exr_sample.csv"))
    assert header[:3] == ["KEY", "FREQ", "CURRENCY"]
    assert len(rows) == 110  # 10 currencies x 11 ECB working days
    first = dict(zip(header, rows[0], strict=True))
    assert first["KEY"] == "EXR.D.AUD.EUR.SP00.A"
    assert first["TIME_PERIOD"] == "2024-12-20"
    assert first["OBS_VALUE"] == "1.6674"


def test_parse_handles_quoted_commas(fixture_bytes):
    header, rows = parse_csv(fixture_bytes("est_sample.csv"))
    row = dict(zip(header, rows[0], strict=True))
    assert row["COVERAGE"].startswith("ESA 2010 Sectors: S.121, S.122")


def test_select_columns_projects_and_nulls_empty(fixture_bytes):
    cfg = load_config()["exr"]
    header, rows = parse_csv(fixture_bytes("exr_sample.csv"))
    out = select_columns(cfg, header, rows)
    assert len(out[0]) == len(cfg.columns)
    names = list(cfg.columns.values())
    row = dict(zip(names, out[0], strict=True))
    assert row["series_key"] == "EXR.D.AUD.EUR.SP00.A"
    assert row["currency"] == "AUD"
    assert row["obs_value"] == "1.6674"


def test_missing_optional_column_becomes_null():
    cfg = load_config()["hicp"]
    body = b"KEY,TIME_PERIOD,OBS_VALUE\r\nHICP.M.U2.N.000000.4D0.ANR,2024-01,2.8\r\n"
    header, rows = parse_csv(body)
    out = select_columns(cfg, header, rows)
    row = dict(zip(cfg.columns.values(), out[0], strict=True))
    assert row["time_period"] == "2024-01" and row["unit"] is None


def test_missing_required_column_fails_loudly():
    cfg = load_config()["hicp"]
    header, rows = parse_csv(b"KEY,TIME_PERIOD\r\nX,2024-01\r\n")
    with pytest.raises(FormatError):
        select_columns(cfg, header, rows)


def test_ragged_row_fails():
    with pytest.raises(FormatError):
        parse_csv(b"A,B\r\n1,2,3\r\n")


def test_empty_body_has_no_rows():
    assert parse_csv(b"") == ([], [])
