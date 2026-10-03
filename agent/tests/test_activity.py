from travel_agent.activity import label
from travel_agent.guard import ToolGuard
from travel_agent.hooks import AgentHooks


def test_labels():
    assert label("search_flights", {"origin": "HYD", "destination": "MAA", "date": "2026-10-17",
                                    "nonstop_only": True, "max_price": 6000}) == \
        "Searching flights HYD → MAA on 2026-10-17 (nonstop, under ₹6,000)"
    assert label("search_policies", {"airlines": ["6E", "dgca"]}) == "Checking fare rules: IndiGo, DGCA rules"
    assert label("get_travel_preferences", {}) == "Reading your preferences"
    assert label("mystery_tool", None) == "Mystery tool"


async def test_events_for_allowed_blocked_and_failed_calls():
    events = []

    async def sink(e):
        events.append(e)

    h = AgentHooks(ToolGuard(max_flight_searches=1), emit=sink)
    s = {"tool_name": "mcp__travel__search_flights", "tool_input": {"origin": "HYD", "destination": "MAA", "date": "d"}}
    assert await h.pre(s, "t1", None) == {}
    await h.post({}, "t1", None)
    s2 = {"tool_name": "mcp__travel__search_flights", "tool_input": {"origin": "HYD", "destination": "BLR", "date": "d"}}
    denied = await h.pre(s2, "t2", None)  # over the 1-search cap
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    await h.pre({"tool_name": "mcp__travel__search_policies", "tool_input": {}}, "t3", None)
    await h.post_failure({"error": "boom"}, "t3", None)

    kinds = [(e["type"], e["id"]) for e in events]
    assert kinds == [("tool_start", "t1"), ("tool_end", "t1"), ("tool_blocked", "t2"),
                     ("tool_start", "t3"), ("tool_end", "t3")]
    assert events[1]["ok"] is True and isinstance(events[1]["duration_ms"], int)
    assert events[4]["ok"] is False and events[4]["error"] == "boom" and events[4]["tool"] == "search_policies"
    assert "t2" not in h.timer.durations_ms  # blocked calls are never timed


def test_sync_sink_supported():
    import asyncio

    seen = []
    h = AgentHooks(ToolGuard(), emit=seen.append)
    asyncio.run(h.pre({"tool_name": "mcp__travel__get_api_usage", "tool_input": {}}, "x", None))
    assert seen[0]["type"] == "tool_start"
