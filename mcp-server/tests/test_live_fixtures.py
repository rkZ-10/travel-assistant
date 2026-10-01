"""Parsers against real recorded responses (scripts/smoke_live.py --record)."""
from travel_mcp.providers.airlabs import collapse_codeshares
from travel_mcp.providers.serpapi import parse_search

from .conftest import load


def test_real_serpapi_response_parses():
    data = load("serpapi_google_flights_DEL_BOM.json")
    res = parse_search(
        data, origin="DEL", destination="BOM", date="2026-10-16",
        return_date=None, currency="INR", limit=100, cached=False,
    )
    assert res.total_found == len(data["best_flights"]) + len(data["other_flights"])
    assert res.price_insights is None  # Google didn't return insights for this search
    for it in res.itineraries:
        assert it.price and it.price > 0
        assert it.segments[0].from_airport == "DEL"
        assert it.segments[-1].to_airport == "BOM"
        assert it.stops == len(it.layovers)
    nonstop = sorted((i for i in res.itineraries if i.stops == 0), key=lambda i: i.price)
    assert nonstop[0].segments[0].flight_number == "AI 2951"


def test_real_airlabs_response_collapses_codeshares():
    rows = load("airlabs_schedules_DEL_BOM.live.json")["response"]
    flights = collapse_codeshares(rows)
    operating = {r["flight_iata"] for r in rows if r.get("cs_flight_iata") is None}
    assert {f.flight_number for f in flights} == operating
    assert len(flights) < len(rows)
    assert all(f.from_airport == "DEL" and f.to_airport == "BOM" for f in flights)
