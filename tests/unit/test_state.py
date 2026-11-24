import pytest

from ecb_ingest.state import WATERMARK_KEY, WatermarkStore


def test_no_watermark_initially(store):
    assert WatermarkStore(store).get("exr") is None


def test_advance_and_read_back(store):
    wm = WatermarkStore(store)
    assert wm.advance("exr", "2026-11-24T17:00:00+00:00", "exr-full-1") is True
    assert wm.get("exr") == "2026-11-24T17:00:00+00:00"
    assert wm.get("est") is None
    assert store.exists(WATERMARK_KEY)


def test_never_moves_backwards(store):
    wm = WatermarkStore(store)
    wm.advance("exr", "2026-11-24T17:00:00+00:00", "a")
    assert wm.advance("exr", "2026-11-23T17:00:00+00:00", "b") is False
    assert wm.advance("exr", "2026-11-24T17:00:00+00:00", "c") is False
    assert wm.read_all()["exr"]["load_id"] == "a"


def test_datasets_are_independent(store):
    wm = WatermarkStore(store)
    wm.advance("exr", "2026-11-24T17:00:00+00:00", "a")
    wm.advance("hicp", "2026-11-20T17:00:00+00:00", "b")
    assert wm.get("exr") == "2026-11-24T17:00:00+00:00"
    assert wm.get("hicp") == "2026-11-20T17:00:00+00:00"


def test_rejects_naive_timestamps(store):
    with pytest.raises(ValueError):
        WatermarkStore(store).advance("exr", "2026-11-24T17:00:00", "a")
