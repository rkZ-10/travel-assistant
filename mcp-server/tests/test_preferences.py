import json

import pytest
from pydantic import ValidationError

from travel_mcp.preferences import PreferenceStore, PreferencesUpdate


@pytest.fixture
def store(tmp_path):
    return PreferenceStore(tmp_path)


def test_empty_by_default(store):
    p = store.load()
    assert p.home_airport is None and p.updated_at is None


def test_update_partial_and_history(store):
    _, diff = store.update(PreferencesUpdate(home_airport="hyd", preferred_airlines=["6e", "qp"], seat="aisle"))
    assert diff["home_airport"] == [None, "HYD"]
    _, diff = store.update(PreferencesUpdate(seat="window"))
    assert diff == {"seat": ["aisle", "window"]}
    p = store.load()
    assert (p.home_airport, p.preferred_airlines, p.seat.value) == ("HYD", ["6E", "QP"], "window")
    history = [json.loads(l) for l in store.history_path.read_text().splitlines()]
    assert len(history) == 2


def test_clear_and_noop(store):
    store.update(PreferencesUpdate(max_price=7000))
    _, diff = store.update(PreferencesUpdate(clear=["max_price"]))
    assert diff == {"max_price": [7000, None]}
    _, diff = store.update(PreferencesUpdate())
    assert diff == {}


@pytest.mark.parametrize("bad", [
    {"home_airport": "Hyderabad"},
    {"preferred_airlines": ["IndiGo"]},
    {"earliest_departure": "7am"},
    {"max_stops": 5},
])
def test_validation(bad):
    with pytest.raises(ValidationError):
        PreferencesUpdate(**bad)


def test_cross_field_rules(store):
    with pytest.raises(ValueError, match="before"):
        store.update(PreferencesUpdate(earliest_departure="20:00", latest_departure="08:00"))
    store.update(PreferencesUpdate(preferred_airlines=["6E"]))
    with pytest.raises(ValueError, match="both preferred and avoided"):
        store.update(PreferencesUpdate(avoid_airlines=["6E"]))
    with pytest.raises(ValueError, match="unknown"):
        store.update(PreferencesUpdate(clear=["favourite_colour"]))
