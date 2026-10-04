import json

from travel_agent.config import AgentConfig
from travel_agent.guard import ToolGuard
from travel_agent.hooks import AgentHooks
from travel_agent.runner import TravelAgent, build_options
from travel_agent.ui_tools import SearchRegistry, build_ui_server

RESULT = {
    "origin": "HYD", "destination": "MAA", "date": "2026-10-17", "return_date": None, "currency": "INR",
    "fetched_at": "2026-10-04T05:00:00+00:00", "links_valid_minutes": 30,
    "itineraries": [
        {"price": 7069, "airlines": ["IndiGo"], "booking_token": "tok-6e243-aaaaaaaa",
         "segments": [{"flight_number": "6E 243", "departs": "2026-10-17 07:05", "arrives": "2026-10-17 08:25"}]},
        {"price": 6839, "airlines": ["Air India Express"], "booking_token": "tok-ix1831-bbbbbbb", "segments": []},
    ],
}


def test_registry_reads_common_response_shapes():
    for shape in [
        RESULT,
        {"content": [{"type": "text", "text": json.dumps(RESULT)}]},
        [{"type": "text", "text": json.dumps(RESULT)}],
        {"structuredContent": RESULT, "content": []},
        json.dumps(RESULT),
    ]:
        reg = SearchRegistry()
        assert reg.record({"origin": "HYD"}, shape) == 2, shape
        entry = reg.by_token["tok-6e243-aaaaaaaa"]
        assert entry["itinerary"]["price"] == 7069 and entry["search"]["destination"] == "MAA"
        assert entry["fetched_at"] == RESULT["fetched_at"]


async def test_cards_use_search_facts_and_reject_unknown_tokens():
    reg = SearchRegistry()
    reg.record({}, RESULT)
    events = []

    async def emit(e):
        events.append(e)

    _, card_tool = build_ui_server(reg, emit)
    ok = await card_tool.handler({"flights": [
        {"booking_token": "tok-6e243-aaaaaaaa", "label": "Best timing", "note": "Saver: cancel ₹4,299 (72h+)"},
        {"booking_token": "tok-made-up-zzzz", "label": "Invented"},
    ]})
    assert not ok.get("is_error") and "Skipped (unknown booking_token): Invented" in ok["content"][0]["text"]
    card = events[0]["cards"][0]
    assert events[0]["type"] == "flight_cards" and len(events[0]["cards"]) == 1
    assert card["itinerary"]["price"] == 7069 and card["label"] == "Best timing" and card["links_valid_minutes"] == 30

    bad = await card_tool.handler({"flights": [{"booking_token": "nope-nope-nope"}]})
    assert bad["is_error"] and len(events) == 1


async def test_hooks_record_search_results_from_post_tool_use():
    h = AgentHooks(ToolGuard())
    await h.pre({"tool_name": "mcp__travel__search_flights", "tool_input": {"origin": "HYD"}}, "t1", None)
    await h.post({"tool_name": "mcp__travel__search_flights", "tool_input": {"origin": "HYD"},
                  "tool_response": [{"type": "text", "text": json.dumps(RESULT)}]}, "t1", None)
    assert "tok-ix1831-bbbbbbb" in h.registry.by_token


async def test_guard_blocks_booking_lookup_and_allows_ui_tool_only_in_web_mode():
    g = ToolGuard()
    d = await g.decide("mcp__travel__get_booking_options", {})
    assert not d.allow and "user clicks" in d.reason
    assert not (await g.decide("mcp__ui__show_flight_cards", {})).allow
    web = ToolGuard(ui_tools=frozenset({"mcp__ui__show_flight_cards"}))
    assert (await web.decide("mcp__ui__show_flight_cards", {})).allow


def test_web_mode_options(monkeypatch):
    monkeypatch.setenv("TRAVEL_MCP_COMMAND", json.dumps(["py", "-m", "travel_mcp.server"]))
    agent = TravelAgent(AgentConfig(), ui=True)
    o = build_options(agent.cfg, agent.hooks, agent.ui_server)
    assert "ui" in o.mcp_servers and "mcp__ui__show_flight_cards" in o.allowed_tools
    assert "show_flight_cards" in o.system_prompt
    cli = build_options(AgentConfig(), ToolGuard())
    assert "ui" not in cli.mcp_servers and "show_flight_cards" not in cli.system_prompt
    assert "mcp__travel__get_booking_options" not in cli.allowed_tools
