import httpx
import pytest

from ecb_ingest.client import EcbApiError, EcbClient, TransientApiError, build_url

BASE = "https://data-api.ecb.europa.eu/service"


def make_client(handler, max_attempts=3):
    return EcbClient(BASE, transport=httpx.MockTransport(handler), max_attempts=max_attempts, backoff_multiplier=0)


def test_build_url_keeps_plus_in_key_and_encodes_timestamp():
    url = build_url(
        BASE,
        "EXR",
        "D.USD+GBP.EUR.SP00.A",
        {
            "format": "csvdata",
            "startPeriod": "2015-01-01",
            "endPeriod": None,
            "updatedAfter": "2026-11-20T18:00:00+00:00",
        },
    )
    assert url == (
        "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+GBP.EUR.SP00.A"
        "?format=csvdata&startPeriod=2015-01-01&updatedAfter=2026-11-20T18%3A00%3A00%2B00%3A00"
    )


def test_fetch_ok_returns_body_unchanged(fixture_bytes):
    body = fixture_bytes("exr_sample.csv")
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=body, headers={"content-type": "application/vnd.sdmx.data+csv"})

    with make_client(handler) as c:
        res = c.fetch("EXR", "D.USD+GBP.EUR.SP00.A", start_period="2024-12-20")
    assert res.has_data and res.status_code == 200
    assert res.body == body
    assert "+GBP" in seen[0]  # the '+' reached the wire un-encoded


def test_fetch_404_problem_json_means_no_data(fixture_bytes):
    body = fixture_bytes("exr_empty.csv")  # real 404 body from the API

    def handler(request):
        return httpx.Response(404, content=body, headers={"content-type": "application/problem+json"})

    with make_client(handler) as c:
        res = c.fetch("EXR", "D.USD.EUR.SP00.A", updated_after="2030-01-01T00:00:00+00:00")
    assert res.has_data is False
    assert res.detail.startswith("No Series was returned")


def test_transient_errors_are_retried_then_succeed(fixture_bytes):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        if calls["n"] == 2:
            return httpx.Response(503)
        return httpx.Response(200, content=fixture_bytes("hicp_sample.csv"))

    with make_client(handler) as c:
        res = c.fetch("HICP", "M.U2.N.000000.4D0.ANR")
    assert res.has_data and calls["n"] == 3


def test_retries_give_up_after_max_attempts():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429)

    with make_client(handler, max_attempts=3) as c, pytest.raises(TransientApiError):
        c.fetch("EXR", "D.USD.EUR.SP00.A")
    assert calls["n"] == 3


def test_client_errors_are_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad query")

    with make_client(handler) as c, pytest.raises(EcbApiError):
        c.fetch("EXR", "D.USD.EUR.SP00.A")
    assert calls["n"] == 1


def test_real_400_html_response_is_not_retried(fixture_bytes):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, content=fixture_bytes("exr_400_fractional_seconds.html"))

    with make_client(handler) as c, pytest.raises(EcbApiError, match="HTTP 400"):
        c.fetch("EXR", "D.USD.EUR.SP00.A", updated_after="2026-11-24T13:28:10.225432+00:00")
    assert calls["n"] == 1
