import pytest

from travel_mcp.providers.airlabs import collapse_codeshares, normalize_flight_number

from .conftest import Recorder, load, make_services


@pytest.mark.parametrize("raw", ["6E853", "6e 853", "6E-853", " 6E  853 "])
def test_normalize(raw):
    assert normalize_flight_number(raw) == "6E853"


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_flight_number("indigo")


def test_codeshares_collapse_to_operating_flights():
    rows = load("airlabs_schedules_DEL_BOM.json")["response"]
    flights = collapse_codeshares(rows)
    assert [f.flight_number for f in flights] == [
        "6E853", "AI2981", "SG2802", "QP1833", "AI2429"
    ]
    six_e = flights[0]
    assert six_e.airline == "6E"
    assert six_e.marketed_as == ["AF3352", "JL9071"]
    assert six_e.departure_gate == "D17"
    delayed = next(f for f in flights if f.flight_number == "AI2429")
    assert delayed.departure_delay_min == 5


async def test_codeshare_number_resolves_to_operator(settings, store):
    payload = load("airlabs_schedules_DEL_BOM.json")
    payload["response"] = [r for r in payload["response"] if r["flight_iata"] == "JL9071"]
    air = Recorder(payload)
    svc = make_services(settings, store, Recorder({}), air)
    result = await svc.status.flight_status("jl 9071")
    assert air.requests[0].url.params["flight_iata"] == "JL9071"
    assert result.flights[0].flight_number == "6E853"
    assert result.flights[0].marketed_as == ["JL9071"]


async def test_second_call_is_cached_and_not_billed(settings, store):
    air = Recorder(load("airlabs_schedules_DEL_BOM.json"))
    svc = make_services(settings, store, Recorder({}), air)
    first = await svc.status.route_departures("DEL", "BOM")
    second = await svc.status.route_departures("DEL", "BOM")
    assert (first.cached, second.cached) == (False, True)
    assert len(air.requests) == 1
    assert store.calls_this_month("airlabs") == 1
