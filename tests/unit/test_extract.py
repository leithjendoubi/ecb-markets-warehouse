from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from ecb_ingest.client import EcbClient
from ecb_ingest.config import load_config
from ecb_ingest.extract import EmptyFullLoadError, Manifest, manifest_key, run_extract
from ecb_ingest.parsing import FormatError
from ecb_ingest.state import WatermarkStore

NOW = datetime(2026, 11, 24, 17, 5, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 25, 17, 5, 0, tzinfo=UTC)


class Api:
    """Fake ECB API (httpx MockTransport) answering with saved real responses."""

    def __init__(self, fixture_bytes, ok="exr_sample.csv", empty_when_updated_after=True):
        self.fixture_bytes = fixture_bytes
        self.ok = ok
        self.empty_when_updated_after = empty_when_updated_after
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        q = parse_qs(urlsplit(str(request.url)).query)
        if "updatedAfter" in q and self.empty_when_updated_after:
            return httpx.Response(
                404, content=self.fixture_bytes("exr_empty.csv"), headers={"content-type": "application/problem+json"}
            )
        return httpx.Response(200, content=self.fixture_bytes(self.ok))

    def client(self) -> EcbClient:
        return EcbClient("https://example.test/service", transport=httpx.MockTransport(self.handler), max_attempts=1)

    def last_query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(str(self.requests[-1].url)).query)


@pytest.fixture
def exr():
    return load_config()["exr"]


def raw_keys(store):
    return store.list_keys("raw/")


def test_first_run_is_full_load_and_lands_bytes_unchanged(exr, store, fixture_bytes):
    api = Api(fixture_bytes)
    m = run_extract(exr, client=api.client(), store=store, watermarks=WatermarkStore(store), now=NOW)
    assert m.mode == "full"
    assert m.load_id == "exr-full-20261124T170500Z"
    assert m.s3_key == "raw/ecb/exr/ingestion_date=2026-11-24/exr-full-20261124T170500Z.csv"
    assert store.get_bytes(m.s3_key) == fixture_bytes("exr_sample.csv")  # unchanged (FR-03)
    assert m.rows_extracted == 110
    assert m.watermark_before is None and m.watermark_candidate == NOW.isoformat()
    q = api.last_query()
    assert q["startPeriod"] == ["2015-01-01"] and "updatedAfter" not in q
    # manifest persisted for the load step
    assert Manifest.from_json(store.get_bytes(manifest_key("exr", m.load_id))) == m


def test_extract_does_not_move_the_watermark(exr, store, fixture_bytes):
    wm = WatermarkStore(store)
    run_extract(exr, client=Api(fixture_bytes).client(), store=store, watermarks=wm, now=NOW)
    assert wm.get("exr") is None  # only the loader advances it, after a successful load


def test_incremental_uses_updated_after_watermark(exr, store, fixture_bytes):
    wm = WatermarkStore(store)
    wm.advance("exr", NOW.isoformat(), "exr-full-x")
    api = Api(fixture_bytes, empty_when_updated_after=False)
    m = run_extract(exr, client=api.client(), store=store, watermarks=wm, now=LATER)
    assert m.mode == "incremental"
    assert api.last_query()["updatedAfter"] == [NOW.isoformat()]
    assert m.watermark_before == NOW.isoformat() and m.watermark_candidate == LATER.isoformat()


def test_second_run_without_new_data_is_a_noop(exr, store, fixture_bytes):
    wm = WatermarkStore(store)
    api = Api(fixture_bytes)
    first = run_extract(exr, client=api.client(), store=store, watermarks=wm, now=NOW)
    wm.advance("exr", first.watermark_candidate, first.load_id)  # what a successful load does
    before = raw_keys(store)

    second = run_extract(exr, client=api.client(), store=store, watermarks=wm, now=LATER)
    assert second.mode == "incremental"
    assert second.rows_extracted == 0 and second.s3_key is None
    assert raw_keys(store) == before  # nothing new landed


def test_full_load_with_no_data_is_an_error(exr, store, fixture_bytes):
    def always_404(request):
        return httpx.Response(404, content=fixture_bytes("exr_empty.csv"))

    client = EcbClient("https://example.test/service", transport=httpx.MockTransport(always_404), max_attempts=1)
    with pytest.raises(EmptyFullLoadError):
        run_extract(exr, client=client, store=store, watermarks=WatermarkStore(store), now=NOW)
    assert raw_keys(store) == []


def test_backfill_is_deterministic_and_rerun_reuses_landing(exr, store, fixture_bytes):
    wm = WatermarkStore(store)
    api = Api(fixture_bytes)
    m1 = run_extract(
        exr, client=api.client(), store=store, watermarks=wm, now=NOW, start="2024-12-20", end="2025-01-08"
    )
    assert m1.mode == "backfill" and m1.load_id == "exr-backfill-2024-12-20-2025-01-08"
    assert api.last_query()["startPeriod"] == ["2024-12-20"] and api.last_query()["endPeriod"] == ["2025-01-08"]
    assert m1.watermark_candidate is None and wm.get("exr") is None

    m2 = run_extract(
        exr, client=api.client(), store=store, watermarks=wm, now=NOW, start="2024-12-20", end="2025-01-08"
    )
    assert m2.load_id == m1.load_id and m2.s3_key == m1.s3_key and m2.rows_extracted == 110
    assert len(raw_keys(store)) == 1  # raw object written once, never overwritten


@pytest.mark.parametrize(
    ("start", "end"), [("2024-01-01", None), (None, "2024-01-01"), ("2024-02-01", "2024-01-01"), ("2024-1-1", "x")]
)
def test_backfill_range_validation(exr, store, fixture_bytes, start, end):
    with pytest.raises(ValueError):
        run_extract(
            exr, client=Api(fixture_bytes).client(), store=store, watermarks=WatermarkStore(store), start=start, end=end
        )


def test_response_missing_required_columns_fails(store, fixture_bytes):
    cfg = load_config()["hicp"]

    def handler(request):
        return httpx.Response(200, content=b"KEY,TIME_PERIOD\r\nHICP.M.U2.N.000000.4D0.ANR,2024-01\r\n")

    client = EcbClient("https://example.test/service", transport=httpx.MockTransport(handler), max_attempts=1)
    with pytest.raises(FormatError):
        run_extract(cfg, client=client, store=store, watermarks=WatermarkStore(store), now=NOW)
    assert raw_keys(store) == []


def test_updated_after_is_sent_in_whole_seconds(exr, store, fixture_bytes):
    """The API rejects fractional seconds with HTTP 400 (seen live, saved as a fixture)."""
    wm = WatermarkStore(store)
    wm.advance("exr", "2026-11-24T13:28:10.225432+00:00", "exr-full-x")
    api = Api(fixture_bytes, empty_when_updated_after=False)
    later = datetime(2026, 11, 25, 17, 5, 0, 987654, tzinfo=UTC)
    m = run_extract(exr, client=api.client(), store=store, watermarks=wm, now=later)
    assert api.last_query()["updatedAfter"] == ["2026-11-24T13:28:10+00:00"]
    assert m.watermark_candidate == "2026-11-25T17:05:00+00:00"
    assert m.load_id == "exr-incremental-20261125T170500Z"
