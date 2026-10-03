import pytest

from travel_agent.guard import ToolGuard

S = "mcp__travel__search_flights"


def search(date="2026-10-16"):
    return {"origin": "HYD", "destination": "MAA", "date": date}


async def test_non_travel_tools_denied():
    g = ToolGuard()
    for name in ["Bash", "WebFetch", "mcp__other__search_flights", "search_flights", "mcp__travel__rm_rf"]:
        assert not (await g.decide(name, {})).allow, name


async def test_read_tools_allowed():
    g = ToolGuard()
    assert (await g.decide("mcp__travel__search_policies", {"query": "x"})).allow


async def test_search_budget_and_repeats():
    g = ToolGuard(max_flight_searches=2)
    assert (await g.decide(S, search("2026-10-16"))).allow
    repeat = await g.decide(S, search("2026-10-16"))
    assert not repeat.allow and "already ran" in repeat.reason
    assert (await g.decide(S, search("2026-10-17"))).allow
    over = await g.decide(S, search("2026-10-18"))
    assert not over.allow and "limit" in over.reason
    g.reset()
    assert (await g.decide(S, search("2026-10-18"))).allow
    assert [d["tool"] for d in g.denied] == [S, S]


async def test_preference_writes_need_approval():
    seen = []

    async def approver(tool, tool_input):
        seen.append((tool, tool_input))
        return tool_input["changes"].get("seat") == "aisle"

    g = ToolGuard(approver=approver)
    ok = await g.decide("mcp__travel__update_travel_preferences", {"changes": {"seat": "aisle"}})
    no = await g.decide("mcp__travel__update_travel_preferences", {"changes": {"seat": "window"}})
    assert ok.allow and not no.allow and "did not approve" in no.reason
    assert seen[0][0] == "update_travel_preferences"


async def test_default_denies_preference_writes():
    g = ToolGuard()
    assert not (await g.decide("mcp__travel__update_travel_preferences", {"changes": {}})).allow


async def test_hook_output_shape():
    g = ToolGuard()
    out = await g.hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "t1", None)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "deny"
    assert await g.hook({"tool_name": "mcp__travel__get_api_usage", "tool_input": {}}, "t2", None) == {}
