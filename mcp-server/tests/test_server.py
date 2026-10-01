from datetime import datetime, timedelta

from mcp import Client

from travel_mcp.server import IST, build_server

from .conftest import Recorder, load, make_services


def future(days: int) -> str:
    return (datetime.now(IST).date() + timedelta(days=days)).isoformat()


def server(settings, store):
    serp = Recorder(load("serpapi_google_flights_DEL_BOM.synthetic.json"))
    air = Recorder(load("airlabs_schedules_DEL_BOM.json"))
    return build_server(make_services(settings, store, serp, air)), serp, air


async def test_tools_listed(settings, store):
    srv, *_ = server(settings, store)
    async with Client(srv) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {
        "search_flights", "get_flight_status", "get_route_departures", "get_api_usage",
        "search_policies", "list_policy_sources",
        "get_travel_preferences", "update_travel_preferences",
    }
    assert tools["update_travel_preferences"].annotations.read_only_hint is False
    assert tools["search_flights"].annotations.read_only_hint is True


async def test_search_ok(settings, store):
    srv, serp, _ = server(settings, store)
    async with Client(srv) as c:
        r = await c.call_tool("search_flights", {"origin": "del", "destination": "bom", "date": future(14)})
    assert not r.is_error
    assert r.structured_content["itineraries"][0]["price"] == 5412
    assert serp.requests[0].url.params["departure_id"] == "DEL"


async def test_search_rejects_bad_input_without_calling_api(settings, store):
    srv, serp, _ = server(settings, store)
    bad = [
        {"origin": "Delhi", "destination": "BOM", "date": future(3)},
        {"origin": "DEL", "destination": "DEL", "date": future(3)},
        {"origin": "DEL", "destination": "BOM", "date": future(-1)},
        {"origin": "DEL", "destination": "BOM", "date": future(5), "return_date": future(2)},
        {"origin": "DEL", "destination": "BOM", "date": future(3), "airlines": ["IndiGo"]},
    ]
    async with Client(srv) as c:
        for args in bad:
            r = await c.call_tool("search_flights", args)
            assert r.is_error, args
    assert serp.requests == []


async def test_route_departures_and_usage(settings, store):
    srv, _, air = server(settings, store)
    async with Client(srv) as c:
        r = await c.call_tool("get_route_departures", {"origin": "DEL", "destination": "BOM"})
        assert len(r.structured_content["flights"]) == 5
        usage = await c.call_tool("get_api_usage", {})
    rows = {row["provider"]: row for row in usage.structured_content["result"]}
    assert rows["airlabs"]["calls_this_month"] == 1
    assert rows["serpapi"]["calls_this_month"] == 0


async def test_missing_key_is_readable_error(settings, store, tmp_path):
    from travel_mcp.config import Settings

    no_keys = Settings(serpapi_key=None, airlabs_key=None, data_dir=tmp_path)
    srv = build_server(make_services(no_keys, store, Recorder({}), Recorder({})))
    async with Client(srv) as c:
        r = await c.call_tool("search_flights", {"origin": "DEL", "destination": "BOM", "date": future(3)})
    assert r.is_error
    assert "SERPAPI_KEY" in r.content[0].text


async def test_preferences_roundtrip_over_mcp(settings, store, tmp_path):
    from travel_mcp.preferences import PreferenceStore

    srv = build_server(make_services(
        settings, store, Recorder({}), Recorder({}), prefs=PreferenceStore(tmp_path)
    ))
    async with Client(srv) as c:
        r = await c.call_tool("update_travel_preferences", {"changes": {"home_airport": "hyd", "seat": "aisle"}})
        assert not r.is_error, r.content
        assert r.structured_content["changed"]["home_airport"] == [None, "HYD"]
        bad = await c.call_tool("update_travel_preferences", {"changes": {"home_airport": "Hyderabad"}})
        assert bad.is_error
        got = await c.call_tool("get_travel_preferences", {})
    assert got.structured_content["home_airport"] == "HYD"
    assert got.structured_content["seat"] == "aisle"


async def test_search_policies_over_mcp(settings, store, tmp_path):
    from travel_mcp.rag.index import PolicyIndex

    from .rag_helpers import AKASA_MD, DGCA_MD, SOURCES, FakeEmbedder, write_snapshot

    empty = PolicyIndex(":memory:", FakeEmbedder())
    srv = build_server(make_services(settings, store, Recorder({}), Recorder({}), policies=empty))
    async with Client(srv) as c:
        r = await c.call_tool("search_policies", {"query": "baggage"})
    assert r.is_error and "travel-rag ingest" in r.content[0].text

    write_snapshot(tmp_path, SOURCES[1], AKASA_MD)
    write_snapshot(tmp_path, SOURCES[2], DGCA_MD)
    idx = PolicyIndex(":memory:", FakeEmbedder())
    idx.rebuild(SOURCES, tmp_path)
    srv = build_server(make_services(settings, store, Recorder({}), Recorder({}), policies=idx))
    async with Client(srv) as c:
        r = await c.call_tool("search_policies", {"query": "checked baggage allowance", "airlines": ["qp"]})
    assert not r.is_error
    top = r.structured_content["passages"][0]
    assert top["airline"] == "QP" and "15 kg" in top["text"]
    assert top["fetched_on"] == "2026-10-02" and top["url"].startswith("https://")
