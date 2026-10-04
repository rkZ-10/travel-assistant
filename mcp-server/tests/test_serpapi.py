import pytest

from travel_mcp.models import SortBy
from travel_mcp.providers.base import ProviderError

from .conftest import Recorder, load, make_services

FIX = "serpapi_google_flights_DEL_BOM.synthetic.json"


async def test_request_params(settings, store):
    serp = Recorder(load(FIX))
    svc = make_services(settings, store, serp, Recorder({}))
    await svc.search.search(
        "DEL", "BOM", "2026-10-16", nonstop_only=True, airlines=["6E", "AI"], sort_by=SortBy.price
    )
    p = serp.requests[0].url.params
    assert p["engine"] == "google_flights"
    assert (p["departure_id"], p["arrival_id"], p["outbound_date"]) == ("DEL", "BOM", "2026-10-16")
    assert p["type"] == "2"  # one way
    assert (p["currency"], p["gl"]) == ("INR", "in")
    assert p["stops"] == "1" and p["sort_by"] == "2"
    assert p["include_airlines"] == "6E,AI"
    assert "return_date" not in p


async def test_parse_results(settings, store):
    svc = make_services(settings, store, Recorder(load(FIX)), Recorder({}))
    res = await svc.search.search("DEL", "BOM", "2026-10-16")
    assert res.total_found == 3
    first = res.itineraries[0]
    assert (first.price, first.stops, first.airlines, first.is_best) == (5412, 0, ["IndiGo"], True)
    assert first.segments[0].flight_number == "6E 6218"
    assert res.itineraries[1].segments[0].often_delayed is True
    connecting = res.itineraries[2]
    assert connecting.stops == 1 and connecting.layovers[0].airport == "HYD"
    assert connecting.layovers[0].overnight is True
    assert res.price_insights.price_level == "typical"


async def test_limit_truncates(settings, store):
    svc = make_services(settings, store, Recorder(load(FIX)), Recorder({}))
    res = await svc.search.search("DEL", "BOM", "2026-10-16", limit=1)
    assert len(res.itineraries) == 1 and res.total_found == 3


async def test_api_error_surfaces(settings, store):
    svc = make_services(
        settings, store, Recorder({"error": "Invalid API key."}, status=401), Recorder({})
    )
    with pytest.raises(ProviderError, match="Invalid API key"):
        await svc.search.search("DEL", "BOM", "2026-10-16")
    assert store.calls_this_month("serpapi") == 1


async def test_max_price_drops_unpriced_and_over_budget(settings, store):
    data = load(FIX)
    data["other_flights"][0]["price"] = None  # Google's "nothing under budget" shape
    svc = make_services(settings, store, Recorder(data), Recorder({}))
    res = await svc.search.search("DEL", "BOM", "2026-10-16", max_price=6000)
    assert [i.price for i in res.itineraries] == [5412]  # 6120 over budget, None unpriced
    assert res.total_found == 1 and "Removed 2" in res.notes[0]


async def test_max_price_nothing_fits_explains(settings, store):
    svc = make_services(settings, store, Recorder(load(FIX)), Recorder({}))
    res = await svc.search.search("DEL", "BOM", "2026-10-16", max_price=1000)
    assert res.itineraries == [] and any("search again without max_price" in n for n in res.notes)


async def test_no_max_price_no_notes(settings, store):
    svc = make_services(settings, store, Recorder(load(FIX)), Recorder({}))
    res = await svc.search.search("DEL", "BOM", "2026-10-16")
    assert res.notes == [] and res.total_found == 3


async def test_booking_options_parsed_airline_first(settings, store):
    serp = Recorder(load("serpapi_booking_options.synthetic.json"))
    svc = make_services(settings, store, serp, Recorder({}))
    res = await svc.search.booking_options("tok-6e243-abcdef", "HYD", "MAA", "2026-10-16")
    p = serp.requests[0].url.params
    assert p["booking_token"] == "tok-6e243-abcdef" and p["departure_id"] == "HYD" and p["type"] == "2"
    assert [(o.seller, o.fare_name, o.price) for o in res.options] == [
        ("IndiGo", "Saver", 7069), ("IndiGo", "Flexi Plus", 8410), ("MakeMyTrip", None, 7012)]
    assert res.options[0].booking_post_data == "u=6e-saver-token" and res.fetched_at
    assert res.notes == [] and res.links_valid_minutes == 10


async def test_booking_options_empty_and_travel_sites_only(settings, store):
    svc = make_services(settings, store, Recorder({"search_metadata": {}, "booking_options": []}), Recorder({}))
    assert "no booking options" in (await svc.search.booking_options("tok-empty-123456", "HYD", "MAA", "2026-10-16")).notes[0]
    data = load("serpapi_booking_options.synthetic.json")
    data["booking_options"] = data["booking_options"][:1]
    svc2 = make_services(settings, store, Recorder(data), Recorder({}))
    res = await svc2.search.booking_options("tok-mmt-only-1234", "HYD", "MAA", "2026-10-16")
    assert "No airline-direct" in res.notes[0]


async def test_search_result_has_fetched_at_and_keeps_it_when_cached(settings, store):
    svc = make_services(settings, store, Recorder(load(FIX)), Recorder({}))
    first = await svc.search.search("DEL", "BOM", "2026-10-16")
    again = await svc.search.search("DEL", "BOM", "2026-10-16")
    assert first.fetched_at and again.cached and again.fetched_at == first.fetched_at
    assert first.links_valid_minutes == 30
