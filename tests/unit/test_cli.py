import json

import pytest

from ecb_ingest import cli
from ecb_ingest.extract import Manifest


def test_parser_lists_configured_datasets():
    args = cli.build_parser().parse_args(
        ["extract", "--dataset", "exr", "--start", "2024-01-01", "--end", "2024-01-31"]
    )
    assert args.dataset == "exr" and args.start == "2024-01-01"
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["extract", "--dataset", "nope"])


def test_extract_prints_json_result_as_last_stdout_line(monkeypatch, capsys, store):
    captured = {}

    def fake_run_extract(cfg, **kwargs):
        captured.update(kwargs)
        return Manifest(
            dataset=cfg.name, load_id="exr-full-x", mode="full", source_url="u", http_status=200, s3_key="k",
            rows_extracted=7, request_started_at="t", ingestion_date="d", watermark_before=None,
            watermark_candidate="t", start_period="2015-01-01", end_period=None,
        )  # fmt: skip

    monkeypatch.setattr(cli, "run_extract", fake_run_extract)
    monkeypatch.setattr(cli, "_store", lambda: store)
    assert cli.main(["extract", "--dataset", "exr", "--run-id", "manual__1"]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last) == {"dataset": "exr", "load_id": "exr-full-x", "rows_extracted": 7}
    assert captured["run_id"] == "manual__1" and captured["start"] is None
