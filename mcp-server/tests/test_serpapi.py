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
