import time

import pytest

from travel_mcp.cache import QuotaExceeded, Store


def test_cache_roundtrip_and_expiry(store, monkeypatch):
    store.set("k", {"a": 1}, ttl=10)
    assert store.get("k") == {"a": 1}
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 11)
    assert store.get("k") is None


def test_api_key_not_part_of_cache_key():
    a = Store.make_key("p", "/x", {"q": 1, "api_key": "secret-1"})
    b = Store.make_key("p", "/x", {"q": 1, "api_key": "secret-2"})
    assert a == b


def test_budget_stops_at_ratio(store):
    for _ in range(9):
        store.record_call("serpapi")
    with pytest.raises(QuotaExceeded):
        store.check_budget("serpapi", budget=10, stop_ratio=0.9)
    store.check_budget("airlabs", budget=10, stop_ratio=0.9)  # other provider unaffected
